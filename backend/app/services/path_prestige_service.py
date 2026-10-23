"""«Академия» prestige: duplicates of the same player raise ONE copy's
prestige tier (Бронза → Серебро → Золото → Икона by default). Status, never
rating:
  * frame / tier marks in every view, profile showcase, «Престиж Академии»
    leaderboard (ranking_service), a global «Икона» number on the top tier;
  * soft bonuses: +experience % per tier (capped), +free Arena attempts a
    day per tier, +quick-sell price % per tier;
  * a one-off reward per tier reached (coins, bought attempts, skill tokens);
  * the top tier unlocks ONE talent reforge for this copy.

Material: duplicates of the SAME player (worth `path_prestige_other_ratio`
units each, 5 by default) or spare copies of OTHER «Академия» players (1
unit each) — a tier costs path_prestige_dupes[tier] × ratio units. A spare
copy of another player is one the owner has more than one of: at least one
copy of every player always stays in the collection.

Tier-ups and reforges are atomic (user lock → card row locks) and
idempotent per (user, idempotency_key) through path_prestige_ledger. All
numbers are GameConfig.path_prestige_* (lists are per tier).
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.card_path import PathPrestigeLedger
from app.models.enums import TransactionType
from app.models.player import Player
from app.models.user import User
from app.services import card_skill_service, path_service
from app.services.game_config_service import get_config
from app.services.path_talent_catalog import TALENTS
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


def _ints(values) -> list[int]:
    return [int(v) for v in (values or [])]


def max_tier(config) -> int:
    return len(_ints(config.path_prestige_dupes))


def tier_name(config, tier: int) -> Optional[str]:
    names = list(config.path_prestige_names or [])
    return names[tier - 1] if 0 < tier <= len(names) else (f"Престиж {tier}" if tier else None)


def xp_bonus_pct(config, tier: int) -> int:
    return min(int(config.path_prestige_xp_cap_pct), tier * int(config.path_prestige_xp_pct))


def extra_free_attempts(config, tier: int) -> int:
    return tier * int(config.path_prestige_free_attempts)


def sell_price(card, config) -> int:
    """Quick-sell price of a copy: prestige raises it (only path cards have
    prestige, so every other card keeps its design price)."""
    tier = getattr(card, "prestige", 0) or 0
    base = card.player.quick_sell_price
    return base + base * tier * int(config.path_prestige_sell_pct) // 100 if tier else base


def reward_for(config, tier: int) -> dict:
    rewards = list(config.path_prestige_rewards or [])
    raw = rewards[tier - 1] if 0 < tier <= len(rewards) else {}
    return {k: max(0, int((raw or {}).get(k, 0) or 0)) for k in ("coins", "attempts", "skill_tokens")}


def _plain(card: UserCard) -> bool:
    """Not locked / in a squad / in a trade, no path progress or prestige of
    its own (burning it must never destroy someone's work)."""
    return card.can_burn() and not card.has_path_progress()


def ratio(config) -> int:
    return max(1, int(config.path_prestige_other_ratio))


def unit_value(card: UserCard, target: UserCard, config) -> int:
    return ratio(config) if card.player_id == target.player_id else 1


async def _free_materials(db: AsyncSession, target: UserCard) -> list[UserCard]:
    """Every copy that may be burnt into `target`: free duplicates of the
    same player first, then spare copies of other «Академия» players (each
    other player keeps its best copy — one with progress, else the lowest
    serial). Copies with a skill come last within each group."""
    rows = (await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(joinedload(UserCard.player))
        .where(UserCard.owner_id == target.owner_id, UserCard.id != target.id, Player.path_talent_code.is_not(None))
        .order_by(UserCard.serial_number)
    )).unique().scalars().all()
    same = [c for c in rows if c.player_id == target.player_id and _plain(c)]
    others: list[UserCard] = []
    by_player: dict[int, list[UserCard]] = {}
    for c in rows:
        if c.player_id != target.player_id:
            by_player.setdefault(c.player_id, []).append(c)
    for copies in by_player.values():
        keeper = sorted(copies, key=lambda c: (not c.has_path_progress(), c.serial_number or 0))[0]
        others.extend(c for c in copies if c is not keeper and _plain(c))
    return sorted(same, key=_skill_last) + sorted(others, key=_skill_last)


def pick_materials(free: list[UserCard], target: UserCard, config, need_units: int) -> list[UserCard]:
    """Automatic pick without waste: whole same-player duplicates while they
    fit, other players' spares for the rest, one more duplicate only if
    nothing else can close the gap. Never copies with a skill."""
    plain = [c for c in free if not c.skill_code]
    same = [c for c in plain if c.player_id == target.player_id]
    others = [c for c in plain if c.player_id != target.player_id]
    chosen, left, r = [], need_units, ratio(config)
    while left >= r and same:
        chosen.append(same.pop(0))
        left -= r
    while left > 0 and others:
        chosen.append(others.pop(0))
        left -= 1
    if left > 0 and same:
        chosen.append(same.pop(0))
        left -= r
    return chosen if left <= 0 else []


def _skill_last(card: UserCard) -> tuple:
    return card.skill_code is not None, card.serial_number or 0


def state_out(card: UserCard, config, free: list[UserCard], catalog=None) -> dict:
    tier, top = card.prestige or 0, max_tier(config)
    dupes, coins = _ints(config.path_prestige_dupes), _ints(config.path_prestige_coins)
    can_reforge = tier >= top > 0 and not card.talent_reforged
    current = path_service.talent_code_of(card)
    options = []
    if can_reforge:
        for code, definition in TALENTS.items():
            row = catalog.talents.get(code) if catalog is not None else None
            if code == current or (row is not None and not row.is_enabled):
                continue
            if definition.positions is not None and card.player.position not in definition.positions:
                continue
            options.append({"code": code, "name": definition.name, "emoji": definition.emoji, "summary": definition.summary})
    return {
        "tier": tier, "max_tier": top, "tier_name": tier_name(config, tier),
        "names": list(config.path_prestige_names or []),
        "next_dupes": dupes[tier] if tier < top else None,
        "ratio": ratio(config),
        "free_units": sum(unit_value(c, card, config) for c in free if not c.skill_code),
        "next_coins": (coins[tier] if tier < len(coins) else 0) if tier < top else None,
        "next_reward": reward_for(config, tier + 1) if tier < top else None,
        "free_duplicates": [
            {"id": c.id, "serial_number": c.serial_number, "skill_code": c.skill_code,
             "player_name": c.player.display_name, "same_player": c.player_id == card.player_id,
             "units": unit_value(c, card, config)}
            for c in free
        ],
        "xp_bonus_pct": xp_bonus_pct(config, tier),
        "next_xp_bonus_pct": xp_bonus_pct(config, tier + 1) if tier < top else None,
        "extra_free_attempts": extra_free_attempts(config, tier),
        "sell_price": sell_price(card, config),
        "icon_number": card.prestige_icon_number,
        "reforged": bool(card.talent_reforged),
        "can_reforge": can_reforge,
        "reforge_options": options,
    }


async def _replay(db: AsyncSession, user_id: int, key: Optional[str]) -> Optional[PathPrestigeLedger]:
    if not key:
        return None
    return (await db.execute(select(PathPrestigeLedger).where(
        PathPrestigeLedger.user_id == user_id, PathPrestigeLedger.idempotency_key == key,
    ))).scalar_one_or_none()


async def _locked_target(db: AsyncSession, user: User, card_id: int) -> UserCard:
    card = (await db.execute(
        select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
        .with_for_update(of=UserCard).execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if card is None or card.owner_id != user.id:
        raise NotFoundError("Карточка не найдена")
    if not path_service.is_path_card(card):
        raise ConflictError("Престиж есть только у карточек «Академии»")
    return card


async def _assign_icon_number(db: AsyncSession, card: UserCard) -> None:
    """Global «Икона» number: the next free one. The unique constraint makes
    a concurrent tier-up that picked the same number retry with the next."""
    for _ in range(5):
        number = int((await db.execute(select(func.max(UserCard.prestige_icon_number)))).scalar_one() or 0) + 1
        try:
            async with db.begin_nested():
                card.prestige_icon_number = number
                db.add(card)
                await db.flush()
            return
        except IntegrityError:
            card.prestige_icon_number = None
    raise ConflictError("Не удалось выдать номер «Иконы» — попробуй ещё раз")


async def tier_up(
    db: AsyncSession, user: User, card_id: int, material_ids: Optional[list[int]], confirm_skill_loss: bool,
    idempotency_key: Optional[str],
) -> dict:
    config = await get_config(db)
    if not config.path_enabled:
        raise ConflictError("Механика «Академия» сейчас выключена")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key) is not None:
        return await get_state(db, user, card_id)
    target = await _locked_target(db, locked_user, card_id)
    top, tier = max_tier(config), target.prestige or 0
    if tier >= top:
        raise ConflictError("Престиж этой карточки уже максимальный")
    need = _ints(config.path_prestige_dupes)[tier]
    coins = (_ints(config.path_prestige_coins) + [0] * top)[tier]

    need_units = need * ratio(config)
    free = await _free_materials(db, target)
    if material_ids:
        by_id = {c.id: c for c in free}
        if len(set(material_ids)) != len(material_ids) or any(i not in by_id for i in material_ids):
            raise ConflictError(
                "Можно вложить только свободные дубли этого игрока или лишние копии других игроков «Академии»",
            )
        chosen = [by_id[i] for i in material_ids]
        units = [unit_value(c, target, config) for c in chosen]
        if sum(units) < need_units:
            raise ConflictError(f"Не хватает: нужно {need_units} ед., выбрано {sum(units)}",
                                details={"need_units": need_units})
        if sum(units) - min(units) >= need_units:
            raise ConflictError("Выбрано больше карточек, чем нужно для ступени", details={"need_units": need_units})
    else:
        chosen = pick_materials(free, target, config, need_units)
    if not chosen:
        free_units = sum(unit_value(c, target, config) for c in free if not c.skill_code)
        raise ConflictError(
            f"Нужно {need} дубл. этого игрока или {need_units} лишних карт других игроков «Академии»",
            details={"need": need, "need_units": need_units, "free_units": free_units},
        )
    materials = (await db.execute(
        select(UserCard).where(UserCard.id.in_([c.id for c in chosen])).options(joinedload(UserCard.player))
        .with_for_update(of=UserCard).execution_options(populate_existing=True)
    )).unique().scalars().all()
    still_free = {c.id for c in await _free_materials(db, target)}
    if len(materials) != len(chosen) or any(c.id not in still_free for c in materials):
        raise ConflictError("Карточки изменились — обнови экран и попробуй снова")
    # Each other player must keep at least one copy after the burn.
    burnt_by_player: dict[int, int] = {}
    for c in materials:
        if c.player_id != target.player_id:
            burnt_by_player[c.player_id] = burnt_by_player.get(c.player_id, 0) + 1
    for player_id, burnt in burnt_by_player.items():
        owned = (await db.execute(select(func.count(UserCard.id)).where(
            UserCard.owner_id == target.owner_id, UserCard.player_id == player_id,
        ))).scalar_one()
        if owned - burnt < 1:
            raise ConflictError("У каждого игрока «Академии» должна остаться хотя бы одна копия")
    card_skill_service.require_skill_loss_confirmation(list(materials), confirm_skill_loss, "престиж «Академии»")

    if coins:
        await debit_coins(
            db, locked_user, coins, TransactionType.path_prestige,
            f"Престиж «{config.path_title}»: {target.player.display_name}",
            related_object_type="user_card", related_object_id=target.id,
        )
    consumed = [c.id for c in materials]
    for c in materials:
        await db.delete(c)
    target.prestige = tier + 1
    db.add(target)
    await db.flush()
    if target.prestige >= top:
        await _assign_icon_number(db, target)

    reward = reward_for(config, target.prestige)
    granted: dict = {}
    if reward["coins"] and not locked_user.game_rewards_blocked:
        await credit_coins(
            db, locked_user, reward["coins"], TransactionType.path_prestige_reward,
            f"Награда за престиж «{tier_name(config, target.prestige)}»",
            related_object_type="user_card", related_object_id=target.id,
        )
        granted["coins"] = reward["coins"]
    if reward["attempts"]:
        catalog = await path_service.load_catalog(db)
        path = await path_service.get_or_create_path(db, target, catalog)
        path.bought_attempts += reward["attempts"]
        db.add(path)
        granted["attempts"] = reward["attempts"]
    if reward["skill_tokens"] and not locked_user.game_rewards_blocked:
        table = await card_skill_service.pack_token_drop_table(db)
        if table:
            code, _qty = card_skill_service.pick_pack_token(table)
            await card_skill_service.grant_tokens(
                db, locked_user, code, reward["skill_tokens"], "grant_prestige",
                related_object_type="user_card", related_object_id=target.id,
                reason=f"Престиж «{tier_name(config, target.prestige)}»",
            )
            granted["skill_tokens"] = {"skill_code": code, "quantity": reward["skill_tokens"]}
    db.add(PathPrestigeLedger(
        user_id=user.id, user_card_id=target.id, kind="tier_up", tier_after=target.prestige,
        consumed_card_ids=consumed, coins_spent=coins, reward=granted, idempotency_key=idempotency_key,
    ))
    await db.commit()
    state = await get_state(db, user, target.id)
    return {**state, "granted": granted, "new_balance": locked_user.balance}


async def reforge(db: AsyncSession, user: User, card_id: int, talent_code: str, idempotency_key: Optional[str]) -> dict:
    config = await get_config(db)
    if not config.path_enabled:
        raise ConflictError("Механика «Академия» сейчас выключена")
    locked_user = await lock_user_for_update(db, user.id)
    if await _replay(db, user.id, idempotency_key) is not None:
        return await get_state(db, user, card_id)
    target = await _locked_target(db, locked_user, card_id)
    catalog = await path_service.load_catalog(db)
    options = {o["code"] for o in state_out(target, config, [], catalog)["reforge_options"]}
    if not state_out(target, config, [], catalog)["can_reforge"]:
        raise ConflictError("Перековка доступна один раз, на высшей ступени престижа")
    if talent_code not in options:
        raise ConflictError("Этот талант нельзя выбрать для перековки")
    before = path_service.talent_code_of(target)
    target.talent_override = talent_code
    target.talent_reforged = True
    db.add(target)
    db.add(PathPrestigeLedger(
        user_id=user.id, user_card_id=target.id, kind="reforge", tier_after=target.prestige, consumed_card_ids=[],
        reward={}, from_talent=before, to_talent=talent_code, idempotency_key=idempotency_key,
    ))
    await db.commit()
    return await get_state(db, user, target.id)


async def get_state(db: AsyncSession, user: User, card_id: int) -> dict:
    return await path_service.get_state(db, user, card_id)


async def showcase(db: AsyncSession, user_id: int, limit: Optional[int] = None) -> list[UserCard]:
    """Profile showcase: the user's most prestigious «Академия» copies — 3
    places plus the «Зал славы» wing's extra ones."""
    if limit is None:
        from app.services.academy_service import SHOWCASE_BASE, user_effects

        limit = SHOWCASE_BASE + (await user_effects(db, user_id, await get_config(db)))["hall"]
    rows = (await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(joinedload(UserCard.player))
        .where(UserCard.owner_id == user_id, Player.path_talent_code.is_not(None), UserCard.prestige > 0)
        .order_by(UserCard.prestige.desc(), (Player.rating + UserCard.path_rating_bonus).desc(), UserCard.id)
        .limit(limit)
    )).unique().scalars().all()
    return list(rows)
