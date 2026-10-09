"""Personal card skills: catalog state, token balances, and the three paid
operations on ONE specific owned card copy (assign / upgrade / replace).

Ownership model: a skill is two columns on the `user_cards` row (one row per
physical copy), so it follows the copy through trades and never touches other
copies of the same player. Old cards keep NULL/NULL — nothing is backfilled.

Transaction shape of every paid operation (single commit):
  idempotency replay check -> lock user (project-wide first lock, same order
  as trades/packs) -> lock the card row -> lock the token row -> verify owner,
  trade/admin locks, the client's confirmed state and price -> debit coins
  (CoinTransaction) and tokens -> change the card -> ledger row -> commit.
A retried request with the same Idempotency-Key is answered from the ledger
row the first attempt wrote (unique (user_id, idempotency_key)), so it can
never charge twice, even when both attempts race (the loser hits the unique
index and replays).

Admin switches:
  * GameConfig.card_skills_enabled = False: no operations at all; new
    matches snapshot no effects; owned skills/tokens are kept; matches that
    already started keep the effects frozen in their own state.
  * CardSkill.is_enabled = False (one skill): that skill can no longer be
    ASSIGNED, UPGRADED or chosen as a REPLACEMENT target; a card that already
    has it keeps it, keeps its match effect, and may still REPLACE it with
    another, enabled skill. Tokens of it can still be granted/held.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, InsufficientBalanceError, NotFoundError
from app.models.card import UserCard
from app.models.card_skill import CardSkill, CardSkillLedger, UserSkillToken
from app.models.enums import Position, TransactionType
from app.models.game_config import GameConfig
from app.models.user import User
from app.schemas.card_skill import (
    CardCopyOut,
    CardSkillOut,
    CardSkillStateOut,
    SkillActionOut,
    SkillCatalogItemOut,
    SkillCatalogOut,
    SkillCostOut,
    SkillCostsOut,
    SkillLevelEffectOut,
    SkillOperationOut,
    SkillOperationRequest,
    SkillRulesOut,
    SkillTokenBalanceOut,
)
from app.services.card_skill_catalog import MAX_SKILL_LEVEL, SKILL_DEFINITIONS, SKILL_ORDER, SkillDefinition, roman
from app.services.card_skill_effects import is_position_compatible, level_bonus_pp
from app.services.game_config_service import get_config
from app.services.wallet_service import debit_coins, lock_user_for_update

GRANT_KINDS = {"grant_task", "grant_tournament", "grant_admin", "revoke_admin"}


# --- Catalog -----------------------------------------------------------------


async def ensure_catalog(db: AsyncSession, commit: bool = True) -> dict[str, CardSkill]:
    """Idempotent seed: one CardSkill row per code in the server catalog
    (migration 0122 seeds the same rows; this covers fresh/test databases).
    Never overwrites admin edits on existing rows. `commit=False` only
    flushes — for callers that are mid-transaction (reward grants) and must
    not commit someone else's half-done work."""
    rows = {r.code: r for r in (await db.execute(select(CardSkill))).scalars().all()}
    missing = [code for code in SKILL_ORDER if code not in rows]
    if not missing:
        return rows
    for index, code in enumerate(SKILL_ORDER):
        if code in missing:
            # A skill the engine cannot model starts closed (and can't be opened).
            row = CardSkill(
                code=code, is_enabled=SKILL_DEFINITIONS[code].engine_supported, allowed_positions=None, sort_order=index,
            )
            db.add(row)
            rows[code] = row
    if not commit:
        await db.flush()
        return rows
    try:
        await db.commit()
    except IntegrityError:
        # A concurrent request seeded the same rows first.
        await db.rollback()
        rows = {r.code: r for r in (await db.execute(select(CardSkill))).scalars().all()}
    return rows


def allowed_positions(definition: SkillDefinition, row: Optional[CardSkill]) -> list[Position]:
    """Admin subset intersected with the server maximum — an admin value can
    only ever narrow the catalog, never widen it."""
    if row is None or row.allowed_positions is None:
        return list(definition.positions)
    subset = {Position(p) for p in row.allowed_positions}
    return [p for p in definition.positions if p in subset]


def acquisition_block_reason(definition: SkillDefinition, row: Optional[CardSkill], config: GameConfig) -> Optional[str]:
    if not config.card_skills_enabled:
        return "Навыки карточек временно отключены"
    if not definition.engine_supported:
        return definition.unavailable_reason or "Навык пока недоступен"
    if row is not None and not row.is_enabled:
        return "Навык временно недоступен для получения"
    return None


def costs(config: GameConfig) -> SkillCostsOut:
    return SkillCostsOut(
        assign=SkillCostOut(token_cost=config.card_skill_assign_token_cost, coin_cost=config.card_skill_assign_coin_cost),
        upgrade_to_2=SkillCostOut(
            token_cost=config.card_skill_upgrade_2_token_cost, coin_cost=config.card_skill_upgrade_2_coin_cost,
        ),
        upgrade_to_3=SkillCostOut(
            token_cost=config.card_skill_upgrade_3_token_cost, coin_cost=config.card_skill_upgrade_3_coin_cost,
        ),
        replace=SkillCostOut(token_cost=config.card_skill_replace_token_cost, coin_cost=config.card_skill_replace_coin_cost),
    )


def _operation_cost(config: GameConfig, operation: str, target_level: int) -> SkillCostOut:
    c = costs(config)
    if operation == "assign":
        return c.assign
    if operation == "replace":
        return c.replace
    return c.upgrade_to_2 if target_level == 2 else c.upgrade_to_3


async def get_catalog(db: AsyncSession) -> SkillCatalogOut:
    config = await get_config(db)
    rows = await ensure_catalog(db)
    skills = []
    for code in SKILL_ORDER:
        definition = SKILL_DEFINITIONS[code]
        row = rows.get(code)
        reason = acquisition_block_reason(definition, row, config)
        skills.append(SkillCatalogItemOut(
            code=code, name=definition.name, icon=definition.icon, effect=definition.effect,
            applies_in=list(definition.applies_in), not_affected=definition.not_affected,
            positions=allowed_positions(definition, row), max_positions=list(definition.positions),
            levels=[
                SkillLevelEffectOut(level=lvl, level_label=roman(lvl), bonus_pp=_capped_bonus(config, lvl))
                for lvl in range(1, MAX_SKILL_LEVEL + 1)
            ],
            engine_supported=definition.engine_supported,
            is_enabled=row.is_enabled if row is not None else True,
            is_available=reason is None, unavailable_reason=reason,
            remaining_work=list(definition.remaining_work),
            sort_order=row.sort_order if row is not None else 0,
        ))
    skills.sort(key=lambda s: s.sort_order)
    return SkillCatalogOut(
        rules=SkillRulesOut(
            enabled=config.card_skills_enabled, max_level=MAX_SKILL_LEVEL,
            event_bonus_cap_pp=config.card_skill_event_bonus_cap_pp,
            probability_floor_pct=config.card_skill_probability_floor_pct,
            probability_ceiling_pct=config.card_skill_probability_ceiling_pct,
            costs=costs(config),
        ),
        skills=skills,
    )


def _capped_bonus(config: GameConfig, level: int) -> int:
    return max(0, min(level_bonus_pp(config, level), config.card_skill_event_bonus_cap_pp))


# --- Tokens --------------------------------------------------------------------


async def get_token_balances(db: AsyncSession, user_id: int) -> dict[str, int]:
    rows = (await db.execute(select(UserSkillToken).where(UserSkillToken.user_id == user_id))).scalars().all()
    return {r.skill_code: r.quantity for r in rows}


def balances_out(balances: dict[str, int]) -> list[SkillTokenBalanceOut]:
    return [SkillTokenBalanceOut(skill_code=code, quantity=balances.get(code, 0)) for code in SKILL_ORDER]


async def _lock_token_row(db: AsyncSession, user_id: int, skill_code: str, create: bool) -> Optional[UserSkillToken]:
    result = await db.execute(
        select(UserSkillToken)
        .where(UserSkillToken.user_id == user_id, UserSkillToken.skill_code == skill_code)
        .with_for_update().execution_options(populate_existing=True)
    )
    row = result.scalar_one_or_none()
    if row is None and create:
        # Safe without ON CONFLICT: every caller already holds the user row
        # lock, which serializes all token writes for this user.
        row = UserSkillToken(user_id=user_id, skill_code=skill_code, quantity=0)
        db.add(row)
        await db.flush()
    return row


def validate_grantable_skill(skill_code: str) -> SkillDefinition:
    definition = SKILL_DEFINITIONS.get(skill_code)
    if definition is None:
        raise NotFoundError("Unknown skill")
    if not definition.engine_supported:
        raise ConflictError(
            "Этот навык пока недоступен — жетоны для него не выдаются",
            details={"reason": "skill_unsupported", "skill_code": skill_code},
        )
    return definition


async def grant_tokens(
    db: AsyncSession, locked_user: User, skill_code: str, quantity: int, kind: str, *,
    related_object_type: Optional[str] = None, related_object_id: Optional[int] = None,
    admin_id: Optional[int] = None, reason: Optional[str] = None, idempotency_key: Optional[str] = None,
) -> Optional[CardSkillLedger]:
    """Adds (or, for revoke_admin, removes) tokens inside the CALLER's
    transaction — the caller holds the user lock and commits, exactly like
    wallet_service.credit_coins. Returns None (no-op) for a zero quantity or
    when `idempotency_key` was already used by this user."""
    assert kind in GRANT_KINDS
    validate_grantable_skill(skill_code)
    if quantity == 0:
        return None
    if idempotency_key is not None:
        existing = await _ledger_by_key(db, locked_user.id, idempotency_key)
        if existing is not None:
            return None
    await ensure_catalog(db, commit=False)
    row = await _lock_token_row(db, locked_user.id, skill_code, create=True)
    if row.quantity + quantity < 0:
        raise ConflictError(
            "Нельзя списать больше жетонов, чем есть у игрока",
            details={"reason": "insufficient_tokens", "available": row.quantity},
        )
    row.quantity += quantity
    db.add(row)
    entry = CardSkillLedger(
        user_id=locked_user.id, kind=kind, skill_code=skill_code, token_delta=quantity,
        token_balance_after=row.quantity, coins_spent=0, admin_id=admin_id,
        related_object_type=related_object_type, related_object_id=related_object_id,
        reason=reason, idempotency_key=idempotency_key,
    )
    db.add(entry)
    return entry


async def grant_place_tokens(db: AsyncSession, locked_user: User, tournament_id: int, rank: int, config: GameConfig) -> None:
    """Player-tournament place reward in tokens (GameConfig.ptour_place_skill_tokens).
    Runs inside conclude_tournament's transaction (tournament row locked);
    the per-tournament idempotency key is a second guard against a re-run."""
    entries = config.ptour_place_skill_tokens or []
    entry = entries[rank - 1] if 0 < rank <= len(entries) else None
    if not entry or not entry.get("skill_code") or int(entry.get("quantity") or 0) <= 0:
        return
    if locked_user.game_rewards_blocked:
        return
    await grant_tokens(
        db, locked_user, entry["skill_code"], int(entry["quantity"]), "grant_tournament",
        related_object_type="player_tournament", related_object_id=tournament_id,
        reason=f"{rank}-е место в турнире #{tournament_id}",
        idempotency_key=f"ptour-place-{tournament_id}",
    )


# --- Card state -------------------------------------------------------------


async def _ledger_by_key(db: AsyncSession, user_id: int, key: str) -> Optional[CardSkillLedger]:
    result = await db.execute(
        select(CardSkillLedger).where(CardSkillLedger.user_id == user_id, CardSkillLedger.idempotency_key == key)
    )
    return result.scalar_one_or_none()


def card_skill_out(card: UserCard, config: GameConfig) -> Optional[CardSkillOut]:
    if not card.skill_code or not card.skill_level:
        return None
    return CardSkillOut(
        code=card.skill_code, level=card.skill_level, level_label=roman(card.skill_level),
        bonus_pp=_capped_bonus(config, card.skill_level),
        is_effective=bool(config.card_skills_enabled) and is_position_compatible(card.skill_code, card.player.position)
        and SKILL_DEFINITIONS.get(card.skill_code) is not None and SKILL_DEFINITIONS[card.skill_code].engine_supported,
    )


def _card_block_reason(card: UserCard, config: GameConfig) -> Optional[str]:
    if not config.card_skills_enabled:
        return "Навыки карточек временно отключены"
    if card.is_locked_by_admin:
        return "Карточка заблокирована администратором"
    if card.is_locked_in_trade:
        return "Карточка участвует в активном обмене — навык нельзя менять, пока обмен не завершён или не отменён"
    return None


def _plan_actions(
    card: UserCard, config: GameConfig, rows: dict[str, CardSkill], balances: dict[str, int], coin_balance: int,
) -> list[SkillActionOut]:
    blocked = _card_block_reason(card, config)
    position = card.player.position
    actions: list[SkillActionOut] = []

    def action(operation: str, code: str, target_level: int, extra_reason: Optional[str]) -> SkillActionOut:
        cost = _operation_cost(config, operation, target_level)
        owned = balances.get(code, 0)
        reason = blocked or extra_reason
        if reason is None and owned < cost.token_cost:
            reason = f"Нужно жетонов: {cost.token_cost}, у тебя: {owned}"
        if reason is None and coin_balance < cost.coin_cost:
            reason = f"Нужно монет: {cost.coin_cost}, у тебя: {coin_balance}"
        return SkillActionOut(
            operation=operation, skill_code=code, target_level=target_level, token_cost=cost.token_cost,
            coin_cost=cost.coin_cost, tokens_owned=owned, allowed=reason is None, reason=reason,
        )

    def target_reason(code: str) -> Optional[str]:
        definition = SKILL_DEFINITIONS[code]
        row = rows.get(code)
        reason = acquisition_block_reason(definition, row, config)
        if reason is None and position not in allowed_positions(definition, row):
            reason = "Не подходит позиции карточки"
        return reason

    if not card.skill_code:
        for code in SKILL_ORDER:
            actions.append(action("assign", code, 1, target_reason(code)))
        return actions

    if card.skill_level < MAX_SKILL_LEVEL:
        current = card.skill_code
        definition = SKILL_DEFINITIONS.get(current)
        reason = None
        if definition is None:
            reason = "Неизвестный навык"
        else:
            reason = acquisition_block_reason(definition, rows.get(current), config)
            if reason is None and not is_position_compatible(current, position):
                reason = "Навык не подходит текущей позиции карточки — его можно только заменить"
        actions.append(action("upgrade", current, card.skill_level + 1, reason))
    for code in SKILL_ORDER:
        if code != card.skill_code:
            actions.append(action("replace", code, 1, target_reason(code)))
    return actions


async def _copies(db: AsyncSession, user_id: int, player_id: int) -> list[CardCopyOut]:
    result = await db.execute(
        select(UserCard).where(UserCard.owner_id == user_id, UserCard.player_id == player_id).order_by(UserCard.serial_number)
    )
    return [
        CardCopyOut(
            id=c.id, serial_number=c.serial_number, skill_code=c.skill_code, skill_level=c.skill_level,
            is_locked_in_trade=c.is_locked_in_trade, is_in_lineup=c.is_in_lineup,
            is_in_tactico_squad=c.is_in_tactico_squad, is_locked_by_admin=c.is_locked_by_admin,
        )
        for c in result.scalars().all()
    ]


async def get_card_state(db: AsyncSession, user: User, card_id: int) -> CardSkillStateOut:
    config = await get_config(db)
    rows = await ensure_catalog(db)
    card = (
        await db.execute(select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player)))
    ).scalar_one_or_none()
    if card is None or card.owner_id != user.id:
        raise NotFoundError("Card not found")
    balances = await get_token_balances(db, user.id)
    next_bonus = None
    if card.skill_level and card.skill_level < MAX_SKILL_LEVEL:
        next_bonus = _capped_bonus(config, card.skill_level + 1)
    return CardSkillStateOut(
        card_id=card.id, serial_number=card.serial_number, player_id=card.player_id,
        player_name=card.player.display_name, position=card.player.position,
        skill=card_skill_out(card, config), next_level_bonus_pp=next_bonus,
        blocked_reason=_card_block_reason(card, config),
        actions=_plan_actions(card, config, rows, balances, (await db.get(User, user.id)).balance),
        copies=await _copies(db, user.id, card.player_id),
    )


# --- Paid operations ------------------------------------------------------------


async def _replay(
    db: AsyncSession, entry: CardSkillLedger, request: SkillOperationRequest, user_id: int, card_id: int,
) -> SkillOperationOut:
    if entry.kind != request.operation or entry.user_card_id != card_id:
        raise ConflictError(
            "Этот ключ идемпотентности уже использован для другой операции",
            details={"reason": "idempotency_key_reused"},
        )
    user = await db.get(User, user_id)
    return SkillOperationOut(
        operation=request.operation, card_id=entry.user_card_id or 0,
        skill_code=entry.to_skill_code or entry.skill_code, skill_level=entry.to_level or 1,
        previous_skill_code=entry.from_skill_code, previous_level=entry.from_level,
        token_cost=-entry.token_delta, coin_cost=entry.coins_spent, tokens_left=entry.token_balance_after,
        new_balance=user.balance if user else 0, replayed=True,
    )


def _stale(card: UserCard, message: str, reason: str) -> ConflictError:
    return ConflictError(message, details={
        "reason": reason, "current_skill_code": card.skill_code, "current_level": card.skill_level,
    })


async def perform_operation(
    db: AsyncSession, user: User, card_id: int, request: SkillOperationRequest, idempotency_key: Optional[str],
) -> SkillOperationOut:
    if idempotency_key:
        existing = await _ledger_by_key(db, user.id, idempotency_key)
        if existing is not None:
            return await _replay(db, existing, request, user.id, card_id)

    config = await get_config(db)
    rows = await ensure_catalog(db)
    if not config.card_skills_enabled:
        raise ConflictError("Навыки карточек временно отключены", details={"reason": "mechanic_disabled"})

    locked_user = await lock_user_for_update(db, user.id)
    card = (
        await db.execute(
            select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player))
            .with_for_update(of=UserCard).execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if card is None or card.owner_id != locked_user.id:
        raise NotFoundError("Card not found")
    block = _card_block_reason(card, config)
    if block is not None:
        raise ConflictError(block, details={"reason": "card_locked"})

    # The player confirmed a specific starting state; anything else means a
    # concurrent change (another tab, a trade, an earlier retry) happened.
    if card.skill_code != request.expected_skill_code or card.skill_level != request.expected_level:
        raise _stale(card, "Навык карточки изменился — обнови экран и проверь стоимость ещё раз", "stale_state")

    operation = request.operation
    previous_code, previous_level = card.skill_code, card.skill_level
    if operation == "assign":
        if previous_code is not None:
            raise _stale(card, "У карточки уже есть навык — его можно улучшить или заменить", "already_has_skill")
        target_code, target_level = request.skill_code, 1
    elif operation == "upgrade":
        if previous_code is None:
            raise _stale(card, "У карточки нет навыка для улучшения", "no_skill")
        if previous_level >= MAX_SKILL_LEVEL:
            raise ConflictError("Навык уже максимального уровня (III)", details={"reason": "max_level"})
        target_code, target_level = previous_code, previous_level + 1
    else:  # replace
        if previous_code is None:
            raise _stale(card, "У карточки нет навыка для замены — назначь новый", "no_skill")
        if request.skill_code == previous_code:
            raise ConflictError("Новый навык совпадает с текущим", details={"reason": "same_skill"})
        target_code, target_level = request.skill_code, 1

    definition = SKILL_DEFINITIONS.get(target_code or "")
    if definition is None:
        raise NotFoundError("Unknown skill")
    block = acquisition_block_reason(definition, rows.get(target_code), config)
    if block is not None:
        raise ConflictError(block, details={"reason": "skill_unavailable", "skill_code": target_code})
    position_ok = (
        is_position_compatible(target_code, card.player.position) if operation == "upgrade"
        else card.player.position in allowed_positions(definition, rows.get(target_code))
    )
    if not position_ok:
        raise ConflictError(
            f"Навык «{definition.name}» не подходит позиции {card.player.position.value}",
            details={"reason": "incompatible_position", "skill_code": target_code},
        )

    cost = _operation_cost(config, operation, target_level)
    if cost.token_cost != request.expected_token_cost or cost.coin_cost != request.expected_coin_cost:
        raise ConflictError(
            "Стоимость изменилась — проверь новую цену и подтверди ещё раз",
            details={"reason": "price_changed", "token_cost": cost.token_cost, "coin_cost": cost.coin_cost},
        )

    token_row = await _lock_token_row(db, locked_user.id, target_code, create=False)
    owned = token_row.quantity if token_row is not None else 0
    if owned < cost.token_cost:
        raise InsufficientBalanceError(
            "Недостаточно жетонов навыка",
            details={"reason": "insufficient_tokens", "required": cost.token_cost, "available": owned, "skill_code": target_code},
        )
    if cost.coin_cost > 0:
        await debit_coins(
            db, locked_user, cost.coin_cost, TransactionType.card_skill_purchase,
            f"Навык «{definition.name}» {roman(target_level)}: "
            + {"assign": "назначение", "upgrade": "улучшение", "replace": "замена"}[operation],
            related_object_type="user_card", related_object_id=card.id,
        )
    if cost.token_cost > 0:
        token_row.quantity -= cost.token_cost
        db.add(token_row)

    card.skill_code, card.skill_level = target_code, target_level
    db.add(card)
    db.add(CardSkillLedger(
        user_id=locked_user.id, kind=operation, skill_code=target_code, token_delta=-cost.token_cost,
        token_balance_after=owned - cost.token_cost, coins_spent=cost.coin_cost, user_card_id=card.id,
        from_skill_code=previous_code, from_level=previous_level, to_skill_code=target_code, to_level=target_level,
        idempotency_key=idempotency_key,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        if idempotency_key:
            existing = await _ledger_by_key(db, user.id, idempotency_key)
            if existing is not None:
                return await _replay(db, existing, request, user.id, card_id)
        raise

    return SkillOperationOut(
        operation=operation, card_id=card.id, skill_code=target_code, skill_level=target_level,
        previous_skill_code=previous_code, previous_level=previous_level,
        token_cost=cost.token_cost, coin_cost=cost.coin_cost, tokens_left=owned - cost.token_cost,
        new_balance=locked_user.balance,
    )


# --- Lifecycle guards ----------------------------------------------------------


def require_skill_loss_confirmation(cards: list[UserCard], confirmed: bool, action: str) -> None:
    """Selling, staking in a rarity upgrade or feeding into a diamond card
    destroys the copy — and its skill, with no token refund. Refuse unless
    the player explicitly confirmed losing exactly these skilled copies."""
    skilled = [c for c in cards if c.skill_code]
    if skilled and not confirmed:
        raise ConflictError(
            f"У карточки есть навык — при действии «{action}» он будет потерян без возврата жетонов",
            details={
                "requires_skill_loss_confirmation": True,
                "cards": [
                    {"id": c.id, "serial_number": c.serial_number, "skill_code": c.skill_code, "skill_level": c.skill_level}
                    for c in skilled
                ],
            },
        )
