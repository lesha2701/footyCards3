"""«Путь дебютанта»: the first days of a player registered after
GameConfig.newbie_since (all knobs are GameConfig.newbie_*).

1. «Пак дебютанта» — the first thing the app shows: a pack of
   newbie_first_pack_rarities (an epic on top).
2. «Твоя команда» — eleven cards, one per Card Arena 4-3-3 slot position,
   then the arena lineup is filled automatically.
3. The first Card Arena match pays a newbie_arena_rarity card.
4. «Попробуй режим» tasks (newbie_tasks): the first game of each mode pays
   its coins (and pack, if set).
5. Day 2 (local calendar day after registration) — newbie_day2_coins;
   day 3 — a newbie_day3_rarity card. The starter offer opens on day 2.

Every card the path gives is bound for newbie_bound_days: it plays, but the
owner's «замок» is on and can't be taken off, and trades refuse it
(UserCard.is_bound) — so the gifts can't be farmed into a main account.

Both packs are ordinary PackOpenings on the carrier pack
(free_pack_pack_slug) with a per-user idempotency key, so a retry replays
the same opening (PackOpenPage shows it like any pack). Claims run under
the user lock plus the progress row lock; `claimed` keeps every step and is
the funnel the admin reads."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.card import UserCard
from app.models.card_collection import CardCollection
from app.models.enums import RARITY_ORDER, CardSource, Rarity, TransactionType
from app.models.game import GameSession
from app.models.game_config import GameConfig
from app.models.newbie import NewbieProgress
from app.models.pack import Pack, PackOpening, PackOpeningCard
from app.models.player import Player
from app.models.user import User
from app.schemas.card import UserCardOut
from app.schemas.monetization import GrantedRewardsOut
from app.schemas.newbie import NewbieClaimOut, NewbieFunnelOut, NewbieFunnelStepOut, NewbieGiftOut, NewbieOut, NewbieTaskOut
from app.schemas.pack import PackOpenResult
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

FIRST_PACK = "first_pack"
SQUAD_PACK = "squad_pack"
ARENA = "arena"
DAY2 = "day2"
DAY3 = "day3"
FINALE = "finale"
# step -> (carrier pack slug, shown name, keep the pack's own name). The
# carriers are hidden packs (is_active=false, migration 0206) so the admin
# can give them their own art; without them the free pack carries the step.
CARRIERS = {
    FIRST_PACK: ("debut", "Пак дебютанта", True),
    SQUAD_PACK: ("debut-team", "Твоя команда", True),
    ARENA: ("debut", "Награда за первый матч", False),
}


def is_newbie(user: User, config: GameConfig) -> bool:
    if not config.newbie_enabled or config.newbie_since is None or user.created_at is None:
        return False
    return ensure_aware(user.created_at) >= ensure_aware(config.newbie_since)


def known_modes() -> set[str]:
    from app.models.enums import GameType
    from app.services.admin_analytics_service import MODE_SOURCES

    return {s.key for s in MODE_SOURCES} | {f"game:{t.value}" for t in GameType}


def _start_day(user: User) -> date:
    return ensure_aware(user.created_at).astimezone(app_timezone()).date()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _progress(db: AsyncSession, user: User, *, lock: bool = False) -> NewbieProgress:
    q = select(NewbieProgress).where(NewbieProgress.user_id == user.id)
    if lock:
        q = q.with_for_update().execution_options(populate_existing=True)
    progress = (await db.execute(q)).scalar_one_or_none()
    if progress is None:
        progress = NewbieProgress(user_id=user.id, started_at=_now(), start_day=_start_day(user), claimed={})
        db.add(progress)
        await db.flush()
    return progress


def _mark(progress: NewbieProgress, code: str, ref: Optional[int] = None) -> None:
    claimed = dict(progress.claimed or {})
    claimed[code] = {"at": _now().isoformat(), "ref": ref}
    progress.claimed = claimed  # new dict: JSON columns don't track in-place edits


async def _arena_matches(db: AsyncSession, user: User) -> int:
    """Finished Card Arena matches since registration."""
    from app.models.enums import MatchStatus
    from app.models.match import Match

    return int((await db.execute(
        select(func.count()).select_from(Match).where(
            Match.user_id == user.id, Match.status != MatchStatus.in_progress,
            Match.created_at >= ensure_aware(user.created_at),
        )
    )).scalar_one())


async def _played(db: AsyncSession, user: User, mode: str) -> bool:
    """A finished game of `mode` since registration (the task popup shows
    when the game is over, not at its start)."""
    since = ensure_aware(user.created_at)
    if mode == ARENA:
        return await _arena_matches(db, user) > 0
    if mode.startswith("game:"):
        from app.models.enums import GameSessionStatus

        q = select(exists().where(
            GameSession.user_id == user.id, GameSession.game_type == mode[5:], GameSession.created_at >= since,
            GameSession.status != GameSessionStatus.in_progress,
        ))
        return bool((await db.execute(q)).scalar())
    from app.services.admin_analytics_service import MODE_SOURCES

    src = next((s for s in MODE_SOURCES if s.key == mode), None)
    if src is None:
        return False
    for col in src.user_cols:
        q = select(src.ts).select_from(src.model)
        if src.join is not None:
            q = q.join(*src.join)
        q = q.where(col == user.id, src.ts >= since).limit(1)
        if (await db.execute(q)).first() is not None:
            return True
    return False


def _day(progress: NewbieProgress, today: Optional[date] = None) -> int:
    return ((today or local_today()) - progress.start_day).days + 1


def _bind(card: UserCard, config: GameConfig) -> None:
    if config.newbie_bound_days > 0:
        card.is_user_locked = True
        card.bound_until = _now() + timedelta(days=config.newbie_bound_days)


async def _pick_player(db: AsyncSession, rarity: Rarity, position=None, exclude: set[int] = frozenset()) -> Player:
    """A random active pack player of `rarity` (and `position`), never one
    already given in this pack; falls back to any rarity for the position,
    then to pack_service.pick_random_player."""
    from app.services.pack_service import _collection_active_filter, pick_random_player

    base = (
        select(Player)
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(
            Player.is_active.is_(True), Player.is_pack_droppable.is_(True), Player.path_talent_code.is_(None),
            _collection_active_filter(), Player.rarity != Rarity.diamond,
        )
    )
    if exclude:
        base = base.where(Player.id.not_in(exclude))
    tries = []
    if position is not None:
        tries += [base.where(Player.rarity == rarity, Player.position == position), base.where(Player.position == position)]
    tries.append(base.where(Player.rarity == rarity))
    for q in tries:
        player = (await db.execute(q.order_by(func.random()).limit(1))).scalar_one_or_none()
        if player is not None:
            return player
    return await pick_random_player(db, rarity)


async def _carrier_pack(db: AsyncSession, config: GameConfig, slug: str) -> Pack:
    pack = (await db.execute(select(Pack).where(Pack.slug == slug))).scalar_one_or_none()
    if pack is None:
        pack = (await db.execute(select(Pack).where(Pack.slug == config.free_pack_pack_slug))).scalar_one_or_none()
    if pack is None:
        pack = (await db.execute(select(Pack).order_by(Pack.price, Pack.id).limit(1))).scalar_one_or_none()
    if pack is None:
        raise ConflictError("Паки ещё не настроены")
    return pack


async def _replay(db: AsyncSession, user: User, opening_id: int, step: str) -> PackOpenResult:
    from app.services.pack_service import get_opening_result

    opening = await db.get(PackOpening, opening_id)
    if opening is None or opening.user_id != user.id:
        raise NotFoundError("Пак не найден")
    result = await get_opening_result(db, user, opening)
    slug, name, keep_own = CARRIERS[step]
    if not (keep_own and result.pack.slug == slug):
        result.pack = result.pack.model_copy(update={"name": name})
    return result


async def _open(
    db: AsyncSession, user: User, config: GameConfig, step: str, slots: list[tuple[Rarity, object]],
) -> PackOpenResult:
    from app.services import collection_service
    from app.services.card_creation import create_user_card

    if not is_newbie(user, config):
        raise ForbiddenError("Путь дебютанта — только для новых игроков")
    locked = await lock_user_for_update(db, user.id)
    progress = await _progress(db, locked, lock=True)
    done = (progress.claimed or {}).get(step)
    if done:
        await db.commit()
        return await _replay(db, locked, done["ref"], step)
    if step == SQUAD_PACK and FIRST_PACK not in (progress.claimed or {}):
        raise ConflictError("Сначала открой «Пак дебютанта»")
    if step == ARENA and not await _played(db, locked, ARENA):
        raise ConflictError("Сначала сыграй матч в Card Arena")

    pack = await _carrier_pack(db, config, CARRIERS[step][0])
    opening = PackOpening(
        user_id=locked.id, pack_id=pack.id, price_paid=0, idempotency_key=f"newbie-{step}", created_at=_now(),
    )
    db.add(opening)
    await db.flush()
    # Never a player the newbie already has: every card of the path is new.
    owned = set((await db.execute(select(UserCard.player_id).where(UserCard.owner_id == locked.id))).scalars().all())
    taken: set[int] = set()
    for rarity, position in slots:
        player = await _pick_player(db, rarity, position, taken | owned)
        taken.add(player.id)
        card = await create_user_card(db, locked.id, player.id, CardSource.newbie, opening.id)
        _bind(card, config)
        db.add(PackOpeningCard(
            opening_id=opening.id, user_card_id=card.id, user_coach_card_id=None, user_stadium_card_id=None,
            is_new=player.id not in owned,
        ))
    await collection_service.grant_collection_rewards_for_new_cards(db, locked, taken)
    _mark(progress, step, opening.id)
    await db.commit()

    if step == SQUAD_PACK:
        # The eleven are in the arena lineup straight away; a failure here
        # (formation rules) only leaves the lineup to the player.
        from app.services import auto_squad_service

        try:
            await auto_squad_service.auto_arena_lineup(db, locked, None)
        except ConflictError:
            await db.rollback()
            await db.refresh(locked)
    return await _replay(db, locked, opening.id, step)


# The newbie's first two Card Arena matches (the first one, then the test
# of the new legendary) are against clearly weaker bots: at your-strength /
# bot-strength ≈ 1.8 the engine wins ~98% and loses ~0.2%, at 2.5 it's a
# rout (arena_balance_table.json) — real matches, just friendly ones.
FIRST_ARENA_BOT_RATIOS = (0.55, 0.4)


async def first_arena_opponent(db: AsyncSession, user: User, config: GameConfig) -> Optional[dict]:
    """The pending opponent of a newbie who hasn't played Card Arena yet
    (match_service._pending_opponent), else None — the regular ladder."""
    if not is_newbie(user, config):
        return None
    played = await _arena_matches(db, user)
    if played >= len(FIRST_ARENA_BOT_RATIOS):
        return None
    import random

    from app.services.arena_ladder_service import BOT_NAMES

    return {
        "user_id": None, "name": random.choice(BOT_NAMES), "avatar_url": None, "points": user.arena_points,
        "bot_ratio": FIRST_ARENA_BOT_RATIOS[played], "bot_style": random.choice(("attacking", "possession", "defensive", "counter")),
        "bot_formation": "4-4-2", "found_at": _now().isoformat(), "newbie_first": True,
    }


async def open_arena_card(db: AsyncSession, user: User) -> PackOpenResult:
    """The card for the first Card Arena match, revealed like a pack."""
    config = await get_config(db)
    return await _open(db, user, config, ARENA, [(Rarity(config.newbie_arena_rarity), None)])


async def open_first_pack(db: AsyncSession, user: User) -> PackOpenResult:
    config = await get_config(db)
    rarities = [Rarity(r) for r in (config.newbie_first_pack_rarities or ["epic"])]
    return await _open(db, user, config, FIRST_PACK, [(r, None) for r in rarities])


async def open_squad_pack(db: AsyncSession, user: User) -> PackOpenResult:
    from app.services.lineup_service import FORMATION_SLOTS

    config = await get_config(db)
    rarity = Rarity(config.newbie_squad_rarity)
    return await _open(db, user, config, SQUAD_PACK, [(rarity, s.ideal_position) for s in FORMATION_SLOTS])


async def get_state(db: AsyncSession, user: User) -> NewbieOut:
    config = await get_config(db)
    if not is_newbie(user, config):
        return NewbieOut(active=False)
    progress = await _progress(db, user)
    state = await _state(db, user, config, progress)
    if not state.active and progress.completed_at is None:
        progress.completed_at = _now()
    await db.commit()
    return state


async def _state(db: AsyncSession, user: User, config: GameConfig, progress: NewbieProgress) -> NewbieOut:
    from app.services.pack_service import _get_pack_or_404

    claimed = progress.claimed or {}
    today_day = _day(progress)
    tasks = []
    for t in config.newbie_tasks or []:
        code = f"task:{t['code']}"
        pack_name = None
        if t.get("pack_id"):
            try:
                pack_name = (await _get_pack_or_404(db, t["pack_id"])).name
            except NotFoundError:
                pack_name = None
        tasks.append(NewbieTaskOut(
            code=t["code"], label=t["label"], path=t.get("path") or "/play", coins=t.get("coins") or 0,
            pack_name=pack_name, claimed=code in claimed,
            played=code in claimed or await _played(db, user, t["mode"]),
        ))
    gifts = [
        NewbieGiftOut(
            day=2, coins=config.newbie_day2_coins, opens_on=progress.start_day + timedelta(days=1),
            ready=today_day >= 2, claimed=DAY2 in claimed,
        ),
        NewbieGiftOut(
            day=3, card_rarity=config.newbie_day3_rarity, opens_on=progress.start_day + timedelta(days=2),
            ready=today_day >= 3, claimed=DAY3 in claimed,
        ),
    ]
    arena_claimed = ARENA in claimed
    done = (
        [FIRST_PACK in claimed, SQUAD_PACK in claimed, arena_claimed]
        + [t.claimed for t in tasks] + [g.claimed for g in gifts]
    )
    from app.services import reward_bundle_service

    return NewbieOut(
        # Every step done, the finale («Путь пройден», badge + reward) last.
        active=FINALE not in claimed, day=today_day,
        finale_ready=all(done) and FINALE not in claimed,
        finale=await reward_bundle_service.describe(db, _finale_bundle(config)),
        first_pack_done=FIRST_PACK in claimed, squad_pack_done=SQUAD_PACK in claimed,
        first_pack_top=max(config.newbie_first_pack_rarities or ["rare"], key=lambda r: RARITY_ORDER[Rarity(r)]),
        arena_played=arena_claimed or await _played(db, user, "arena"), arena_claimed=arena_claimed,
        arena_rarity=config.newbie_arena_rarity, tasks=tasks, gifts=gifts, bound_days=config.newbie_bound_days,
        steps_done=sum(done), steps_total=len(done),
    )


def _finale_bundle(config: GameConfig):
    from app.services.reward_bundle_service import Bundle

    return Bundle(
        coins=config.newbie_finale_coins, pack_id=config.newbie_finale_pack_id, badge_id=config.newbie_finale_badge_id,
    )


async def _give_card(db: AsyncSession, user: User, config: GameConfig, rarity: str, out: GrantedRewardsOut) -> None:
    from app.services import collection_service
    from app.services.card_creation import create_user_card

    player = await _pick_player(db, Rarity(rarity))
    card = await create_user_card(db, user.id, player.id, CardSource.newbie)
    _bind(card, config)
    await db.flush()
    card = (await db.execute(
        select(UserCard).where(UserCard.id == card.id).options(joinedload(UserCard.player))
    )).unique().scalar_one()
    out.cards.append(UserCardOut.model_validate(card))
    await collection_service.grant_collection_rewards_for_new_cards(db, user, [player.id])


async def claim(db: AsyncSession, user: User, code: str) -> NewbieClaimOut:
    config = await get_config(db)
    if not is_newbie(user, config):
        raise ForbiddenError("Путь дебютанта — только для новых игроков")
    locked = await lock_user_for_update(db, user.id)
    progress = await _progress(db, locked, lock=True)
    if code in (progress.claimed or {}):
        raise ConflictError("Награда уже получена")
    out = GrantedRewardsOut()
    today_day = _day(progress)

    if code == DAY2:
        if today_day < 2:
            raise ConflictError("Подарок откроется завтра")
        if config.newbie_day2_coins > 0:
            await credit_coins(db, locked, config.newbie_day2_coins, TransactionType.newbie_reward, "Путь дебютанта: день 2")
            out.coins = config.newbie_day2_coins
    elif code == DAY3:
        if today_day < 3:
            raise ConflictError("Подарок откроется на третий день")
        await _give_card(db, locked, config, config.newbie_day3_rarity, out)
    elif code.startswith("task:"):
        task = next((t for t in config.newbie_tasks or [] if t["code"] == code[5:]), None)
        if task is None:
            raise NotFoundError("Задание не найдено")
        if not await _played(db, locked, task["mode"]):
            raise ConflictError("Сначала сыграй в этот режим")
        if task.get("coins"):
            await credit_coins(db, locked, task["coins"], TransactionType.newbie_reward, f"Путь дебютанта: {task['label']}")
            out.coins = task["coins"]
        if task.get("pack_id"):
            from app.services.pack_service import grant_bonus_pack_opening

            opened = await grant_bonus_pack_opening(
                db, locked, task["pack_id"], idempotency_prefix=f"newbie-{code}", source=CardSource.newbie,
            )
            if opened is not None:
                out.pack_name = opened.pack.name
                for item in opened.cards:
                    card = await db.get(UserCard, item.card.id)
                    _bind(card, config)
                    out.cards.append(item.card.model_copy(update={"bound_until": card.bound_until, "is_user_locked": card.is_user_locked}))
    elif code == FINALE:
        if not (await _state(db, locked, config, progress)).finale_ready:
            raise ConflictError("Сначала пройди все шаги пути")
        from app.services import reward_bundle_service

        out = await reward_bundle_service.grant(
            db, locked, _finale_bundle(config), tx_type=TransactionType.newbie_reward,
            description="Путь дебютанта пройден", card_source=CardSource.newbie,
            idempotency_prefix=f"newbie-finale-{locked.id}", cosmetic_source="newbie",
        )
    else:
        raise NotFoundError("Шаг не найден")

    _mark(progress, code)
    out.new_balance = locked.balance
    state = await _state(db, locked, config, progress)
    if not state.active and progress.completed_at is None:
        progress.completed_at = _now()
    await db.commit()
    return NewbieClaimOut(rewards=out, state=state)


async def funnel(db: AsyncSession, days: int) -> NewbieFunnelOut:
    """How far the players who started the path in the last `days` days got."""
    config = await get_config(db)
    since = _now() - timedelta(days=days)
    rows = (await db.execute(
        select(NewbieProgress.claimed, NewbieProgress.completed_at).where(NewbieProgress.started_at >= since)
    )).all()
    steps = [(FIRST_PACK, "Открыл «Пак дебютанта»"), (SQUAD_PACK, "Открыл «Твоя команда»"), (ARENA, "Забрал награду за Арену")]
    steps += [(f"task:{t['code']}", t["label"]) for t in config.newbie_tasks or []]
    steps += [(DAY2, "Забрал подарок 2-го дня"), (DAY3, "Забрал подарок 3-го дня"), (FINALE, "Прошёл путь целиком")]
    return NewbieFunnelOut(
        days=days, started=len(rows), completed=sum(1 for r in rows if r.completed_at is not None),
        steps=[
            NewbieFunnelStepOut(code=code, label=label, players=sum(1 for r in rows if code in (r.claimed or {})))
            for code, label in steps
        ],
    )
