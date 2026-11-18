import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.bingo import BingoCard, BingoGoalDefinition, BingoState, BingoWeek, BingoWeekGoal, BingoWeekReward
from app.models.card import UserCard
from app.models.enums import (
    BingoGoalType,
    CardSource,
    MatchStatus,
    PenaltyMatchStatus,
    Rarity,
    TacticoMatchStatus,
    TradeStatus,
    TransactionType,
)
from app.models.match import Match
from app.models.pack import PackOpening, PackOpeningCard
from app.models.penalty import PenaltyMatch
from app.models.player import Player
from app.models.tactico import TacticoMatch
from app.models.trade import TradeOffer
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
from app.models.user_stadium_card import UserStadiumCard
from app.schemas.bingo import (
    BingoCardCellOut, BingoCardOut, BingoClaimResult, BingoCurrentOut, BingoGoalOut, BingoStatsPreviewItem,
)
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

WEEK_DURATION = timedelta(days=7)

# ---------------------------------------------------------------------------
# The player's own 3×3 card. Every cell is a «played:<mode>»-style metric
# (newbie_service.games_played over the week) or "packs" (paid pack opens);
# the centre is free. Targets are drawn per player and week from [min, max].
# GameConfig.bingo_pool overrides this list.
# ---------------------------------------------------------------------------

FREE = "free"
PACKS = "packs"
DEFAULT_POOL: list[dict] = [
    {"metric": "played:arena", "label": "Матчи Card Arena", "path": "/play/arena", "min": 3, "max": 6},
    {"metric": "played:tactico", "label": "Матчи Тактико", "path": "/play/tactico", "min": 2, "max": 4},
    {"metric": "played:stratego", "label": "Партии Стратего", "path": "/play/stratego", "min": 1, "max": 2},
    {"metric": "played:penalty_pvp", "label": "Пенальти с соперником", "path": "/play/penalty/matches", "min": 1, "max": 3},
    {"metric": "played:blackjack", "label": "Раздачи «21»", "path": "/play/blackjack", "min": 3, "max": 6},
    {"metric": "played:lucky_board", "label": "Запуски «Табло удачи»", "path": "/play/lucky-board", "min": 5, "max": 10},
    {"metric": "played:magic", "label": "Походы «Мяч и Магия»", "path": "/play/magic", "min": 1, "max": 2},
    {"metric": "played:kontra", "label": "Бои «Контратаки»", "path": "/play/kontra", "min": 2, "max": 4},
    {"metric": "played:mordoboi", "label": "Бои «Мордобоя»", "path": "/play/mordoboi", "min": 1, "max": 3},
    {"metric": "played:wheel", "label": "Вращения колеса", "path": "/wheel", "min": 2, "max": 4},
    {"metric": "game:penalty", "label": "Серии Пенальти", "path": "/play/penalty", "min": 3, "max": 6},
    {"metric": "game:free_kick", "label": "Штрафные удары", "path": "/play/free-kick", "min": 3, "max": 6},
    {"metric": "game:memory_sequence", "label": "Игры Memory", "path": "/play/memory", "min": 2, "max": 4},
    {"metric": "game:football_hangman", "label": "Футбольные буквы", "path": "/play/hangman", "min": 2, "max": 4},
    {"metric": "game:saboteur", "label": "Игры «Саботёр»", "path": "/play/saboteur", "min": 2, "max": 4},
    {"metric": "game:one_on_one", "label": "Атаки 1 на 1", "path": "/play/one-on-one", "min": 2, "max": 4},
    {"metric": "game:otvetka", "label": "Матчи «Ответки»", "path": "/play/otvetka", "min": 1, "max": 3},
    {"metric": "game:fergie_time", "label": "Матчи «Ферги Тайм»", "path": "/play/fergie-time", "min": 1, "max": 2},
    {"metric": PACKS, "label": "Открытые паки", "path": "/packs", "min": 2, "max": 4},
]
FREE_CELL = {"metric": FREE, "label": "Бесплатная клетка", "target": 1}
CENTRE = 4
# Rows, columns and the two diagonals of the 3×3 card, cells numbered 0..8 row by row.
LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6),
)


def _pool(config) -> list[dict]:
    """The card pool without the modes an admin switched off."""
    from app.services.task_service import MODE_SWITCHES

    off = {f"played:{mode}" for mode, flag in MODE_SWITCHES.items() if not getattr(config, flag, True)}
    return [c for c in (config.bingo_pool or DEFAULT_POOL) if c.get("metric") not in off]


def draw_cells(pool: list[dict], seed: str) -> list[dict]:
    """Nine cells for one card: eight distinct pool entries around a free
    centre (repeats only when the pool is smaller than eight)."""
    rng = random.Random(seed)
    picks = rng.sample(pool, 8) if len(pool) >= 8 else [rng.choice(pool) for _ in range(8)]
    cells = []
    for entry in picks:
        low = int(entry.get("min", 1))
        high = int(entry.get("max", low))
        cells.append({
            "metric": entry["metric"], "label": entry.get("label", entry["metric"]), "path": entry.get("path"),
            "target": max(1, rng.randint(min(low, high), max(low, high))),
        })
    cells.insert(CENTRE, dict(FREE_CELL))
    return cells


async def _cell_value(db: AsyncSession, user: User, metric: str, since: datetime, until: datetime) -> int:
    if metric == FREE:
        return 1
    if metric == PACKS:
        return int((await db.execute(select(func.count(PackOpening.id)).where(
            PackOpening.user_id == user.id, PackOpening.price_paid > 0,
            PackOpening.created_at >= since, PackOpening.created_at < until,
        ))).scalar_one())
    from app.services.newbie_service import games_played

    mode = metric[len("played:"):] if metric.startswith("played:") else metric
    return await games_played(db, user, mode, since=since, until=until)


async def ensure_card(db: AsyncSession, user: User, week: BingoWeek) -> BingoCard:
    """This week's card of the player, drawn on first sight (seeded by week
    and player, so a racing request draws the very same one)."""
    q = select(BingoCard).where(BingoCard.week_id == week.id, BingoCard.user_id == user.id)
    card = (await db.execute(q)).scalar_one_or_none()
    if card is not None:
        return card
    config = await get_config(db)
    try:
        async with db.begin_nested():
            db.add(BingoCard(
                week_id=week.id, user_id=user.id, cells=draw_cells(_pool(config), f"{week.id}:{user.id}"),
                lines_claimed=[], full_claimed=False, created_at=datetime.now(timezone.utc),
            ))
            await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
    return (await db.execute(q)).scalar_one()


async def _card_progress(
    db: AsyncSession, user: User, week: BingoWeek, card: BingoCard,
) -> tuple[list[int], list[int], bool]:
    """(value per cell, indices of the closed lines, whole card closed)."""
    since, until = ensure_aware(week.starts_at), ensure_aware(week.ends_at)
    values = [await _cell_value(db, user, c["metric"], since, until) for c in card.cells]
    done = [v >= c["target"] for v, c in zip(values, card.cells)]
    lines = [i for i, line in enumerate(LINES) if all(done[j] for j in line)]
    return values, lines, all(done)


async def card_out(db: AsyncSession, user: User, week: BingoWeek, config) -> BingoCardOut:
    card = await ensure_card(db, user, week)
    values, lines, full = await _card_progress(db, user, week, card)
    full_pack_name = None
    if config.bingo_full_pack_id:
        from app.models.pack import Pack

        pack = await db.get(Pack, config.bingo_full_pack_id)
        full_pack_name = pack.name if pack is not None else None
    claimed = set(card.lines_claimed or [])
    pay_full = full and not card.full_claimed
    claimable = len([i for i in lines if i not in claimed]) * config.bingo_line_coins
    if pay_full:
        claimable += config.bingo_full_coins
    return BingoCardOut(
        cells=[
            BingoCardCellOut(
                metric=c["metric"], label=c["label"], path=c.get("path"), target=c["target"],
                value=min(v, c["target"]), done=v >= c["target"], free=c["metric"] == FREE,
            )
            for c, v in zip(card.cells, values)
        ],
        lines=[list(line) for line in LINES], lines_done=lines, lines_claimed=sorted(claimed),
        full_done=full, full_claimed=card.full_claimed,
        line_coins=config.bingo_line_coins, full_coins=config.bingo_full_coins, full_pack_name=full_pack_name,
        claimable_coins=claimable, can_claim=bool(set(lines) - claimed) or pay_full,
        community_eligible=bool(lines),
    )


async def claim_card(db: AsyncSession, user: User) -> BingoClaimResult:
    """Pays every closed line not paid yet and, once all nine cells are done,
    the whole card. Only while the week runs, like the community reward.
    Under the user and card row locks, so a double tap pays once."""
    week = await get_or_create_current_week(db)
    if week is None:
        raise ConflictError("Бинго недели сейчас не идёт")
    card = await ensure_card(db, user, week)
    _, lines, full = await _card_progress(db, user, week, card)
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    card = (await db.execute(
        select(BingoCard).where(BingoCard.id == card.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    claimed = set(card.lines_claimed or [])
    new_lines = [i for i in lines if i not in claimed]
    pay_full = full and not card.full_claimed
    if not new_lines and not pay_full:
        raise ConflictError("Нечего забирать: закрой линию в своей карточке")
    coins = len(new_lines) * config.bingo_line_coins + (config.bingo_full_coins if pay_full else 0)
    granted_pack = None
    if locked_user.game_rewards_blocked:
        coins = 0
    else:
        if coins > 0:
            await credit_coins(
                db, locked_user, coins, TransactionType.bingo_reward, "Бинго недели: моя карточка", "bingo_card", card.id,
            )
        if pay_full and config.bingo_full_pack_id:
            from app.services.pack_service import grant_bonus_pack_opening

            granted_pack = await grant_bonus_pack_opening(
                db, locked_user, config.bingo_full_pack_id, idempotency_prefix=f"bingo-card-{card.id}",
            )
    card.lines_claimed = sorted(claimed | set(new_lines))  # a new list: JSON columns don't track in-place edits
    card.full_claimed = card.full_claimed or pay_full
    card.coins_granted += coins
    await db.commit()
    await db.refresh(locked_user)
    return BingoClaimResult(coins_granted=coins, granted_pack=granted_pack, new_balance=locked_user.balance)


async def _get_or_create_state(db: AsyncSession) -> BingoState:
    """Lazily creates the id=1 singleton row if missing — mirrors
    game_config_service.get_config, and covers the test DB (built from
    Base.metadata, not the migration that seeds this row in real Postgres)."""
    state = await db.get(BingoState, 1)
    if state is None:
        state = BingoState(id=1, is_enabled=False, started_at=None)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


# ---------------------------------------------------------------------------
# Weekly rollover — lazy sweep, same pattern as tactico_service's overdue-
# round sweep: whichever request notices a week is over resolves it and
# creates the next one, no background scheduler required.
# ---------------------------------------------------------------------------

async def get_or_create_current_week(db: AsyncSession) -> Optional[BingoWeek]:
    state = await _get_or_create_state(db)
    if not state.is_enabled or state.started_at is None:
        return None

    now = datetime.now(timezone.utc)
    started_at = ensure_aware(state.started_at)
    expected_week_number = int((now - started_at) / WEEK_DURATION) + 1

    result = await db.execute(select(BingoWeek).order_by(BingoWeek.week_number.desc()).limit(1))
    latest = result.scalar_one_or_none()

    while latest is None or latest.week_number < expected_week_number:
        if latest is not None and not latest.reward_resolved:
            await _resolve_week(db, latest)

        next_number = 1 if latest is None else latest.week_number + 1
        starts_at = started_at + (next_number - 1) * WEEK_DURATION
        ends_at = starts_at + WEEK_DURATION

        try:
            # SAVEPOINT, not a full commit — a concurrent request creating
            # the same week only loses this one insert, not anything else
            # already pending on the session (same trick as
            # lineup_service._get_or_create_lineup).
            async with db.begin_nested():
                new_week = BingoWeek(week_number=next_number, starts_at=starts_at, ends_at=ends_at)
                db.add(new_week)
                await db.flush()

                defs_result = await db.execute(
                    select(BingoGoalDefinition).where(BingoGoalDefinition.is_active.is_(True))
                )
                for definition in defs_result.scalars().all():
                    db.add(
                        BingoWeekGoal(
                            week_id=new_week.id, goal_type=definition.goal_type,
                            target_value=definition.target_value, current_value=0,
                        )
                    )
                await db.flush()
            await db.commit()
        except IntegrityError:
            await db.rollback()

        result = await db.execute(select(BingoWeek).where(BingoWeek.week_number == next_number))
        latest = result.scalar_one()

    return latest


async def _resolve_week(db: AsyncSession, week: BingoWeek) -> None:
    """End-of-week bookkeeping only — records whether the week succeeded,
    for admin/historical display. Reward crediting is NOT done here: it is
    manual (see claim_reward), and only available while the week that
    earned it is still current — once rollover replaces it, an unclaimed
    reward is simply gone, same as a week that fell short."""
    result = await db.execute(select(BingoWeek).where(BingoWeek.id == week.id).with_for_update())
    locked_week = result.scalar_one()
    if locked_week.reward_resolved:
        return

    goals = (await db.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == locked_week.id))).scalars().all()
    all_completed = len(goals) > 0 and all(g.current_value >= g.target_value for g in goals)
    locked_week.all_goals_completed = all_completed
    locked_week.reward_resolved = True
    db.add(locked_week)
    await db.commit()


async def claim_reward(db: AsyncSession, user: User) -> BingoClaimResult:
    week = await get_or_create_current_week(db)
    if week is None:
        raise ConflictError("Bingo недели сейчас не идёт")

    goals = (await db.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week.id))).scalars().all()
    if not goals or not all(g.current_value >= g.target_value for g in goals):
        raise ConflictError("Не все цели недели ещё выполнены")
    # The server's common goal pays only those who played the week
    # themselves: at least one closed line on their own card.
    card = await ensure_card(db, user, week)
    if not (await _card_progress(db, user, week, card))[1]:
        raise ConflictError("Общая награда — тем, кто закрыл хотя бы одну линию в своей карточке")

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)

    try:
        async with db.begin_nested():
            coins_granted = 0
            granted_pack = None
            if not locked_user.game_rewards_blocked:
                if config.bingo_reward_coins > 0:
                    coins_granted = config.bingo_reward_coins
                    await credit_coins(
                        db, locked_user, coins_granted, TransactionType.bingo_reward,
                        "Награда за Бинго недели", "bingo_week", week.id,
                    )
                if config.bingo_reward_pack_id:
                    # Deferred: pack_service imports task_service at module
                    # level (which imports this module for the pack-open
                    # hook), so a top-level import here would be circular.
                    from app.services.pack_service import grant_bonus_pack_opening

                    granted_pack = await grant_bonus_pack_opening(
                        db, locked_user, config.bingo_reward_pack_id,
                        idempotency_prefix=f"bingo-week-{week.id}-{locked_user.id}",
                    )
            db.add(
                BingoWeekReward(
                    week_id=week.id, user_id=locked_user.id, coins_granted=coins_granted,
                    pack_id_granted=config.bingo_reward_pack_id if granted_pack else None,
                    granted_at=datetime.now(timezone.utc),
                )
            )
            await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Награда за эту неделю уже получена") from None

    await db.commit()
    await db.refresh(locked_user)
    return BingoClaimResult(coins_granted=coins_granted, granted_pack=granted_pack, new_balance=locked_user.balance)


async def increment_goal(db: AsyncSession, goal_type: BingoGoalType, amount: int = 1) -> None:
    if amount <= 0:
        return
    week = await get_or_create_current_week(db)
    if week is None:
        return
    result = await db.execute(
        select(BingoWeekGoal).where(BingoWeekGoal.week_id == week.id, BingoWeekGoal.goal_type == goal_type)
    )
    goal = result.scalar_one_or_none()
    if goal is None:
        # This goal wasn't active when the current week started — admin
        # additions only take effect from the next week's snapshot.
        return
    goal.current_value += amount
    db.add(goal)
    await db.commit()


async def get_current_week_out(db: AsyncSession, user: User) -> BingoCurrentOut:
    state = await _get_or_create_state(db)
    if not state.is_enabled:
        return BingoCurrentOut(is_enabled=False)

    week = await get_or_create_current_week(db)
    if week is None:
        return BingoCurrentOut(is_enabled=False)

    goals = (await db.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week.id))).scalars().all()
    goal_outs = [
        BingoGoalOut(
            goal_type=g.goal_type, target_value=g.target_value, current_value=g.current_value,
            is_completed=g.current_value >= g.target_value,
        )
        for g in goals
    ]
    all_completed = len(goal_outs) > 0 and all(g.is_completed for g in goal_outs)

    config = await get_config(db)
    reward_pack_name = None
    reward_pack_image_path = None
    if config.bingo_reward_pack_id:
        from app.models.pack import Pack

        pack = await db.get(Pack, config.bingo_reward_pack_id)
        if pack is not None:
            reward_pack_name = pack.name
            reward_pack_image_path = pack.image_path

    has_claimed = (
        await db.execute(
            select(BingoWeekReward).where(BingoWeekReward.week_id == week.id, BingoWeekReward.user_id == user.id)
        )
    ).scalar_one_or_none() is not None

    return BingoCurrentOut(
        is_enabled=True, week_number=week.week_number, starts_at=week.starts_at, ends_at=week.ends_at,
        goals=goal_outs, all_goals_completed=all_completed,
        reward_coins=config.bingo_reward_coins, reward_pack_id=config.bingo_reward_pack_id,
        reward_pack_name=reward_pack_name, reward_pack_image_path=reward_pack_image_path,
        has_claimed=has_claimed,
        card=await card_out(db, user, week, config),
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def get_state(db: AsyncSession) -> BingoState:
    return await _get_or_create_state(db)


async def set_enabled(db: AsyncSession, is_enabled: bool) -> BingoState:
    state = await _get_or_create_state(db)
    state.is_enabled = is_enabled
    if is_enabled and state.started_at is None:
        state.started_at = datetime.now(timezone.utc)
    db.add(state)
    await db.flush()
    return state


async def list_goal_definitions(db: AsyncSession) -> list[BingoGoalDefinition]:
    result = await db.execute(select(BingoGoalDefinition).order_by(BingoGoalDefinition.goal_type))
    return list(result.scalars().all())


async def _assert_no_other_active(db: AsyncSession, goal_type: BingoGoalType, exclude_id: Optional[int] = None) -> None:
    query = select(BingoGoalDefinition).where(
        BingoGoalDefinition.goal_type == goal_type, BingoGoalDefinition.is_active.is_(True)
    )
    if exclude_id is not None:
        query = query.where(BingoGoalDefinition.id != exclude_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise ConflictError(f"An active goal for {goal_type.value} already exists")


async def create_goal_definition(
    db: AsyncSession, goal_type: BingoGoalType, target_value: int, is_active: bool
) -> BingoGoalDefinition:
    if is_active:
        await _assert_no_other_active(db, goal_type)
    definition = BingoGoalDefinition(goal_type=goal_type, target_value=target_value, is_active=is_active)
    db.add(definition)
    await db.flush()
    return definition


async def update_goal_definition(
    db: AsyncSession, definition_id: int, target_value: Optional[int], is_active: Optional[bool]
) -> BingoGoalDefinition:
    definition = await db.get(BingoGoalDefinition, definition_id)
    if definition is None:
        raise NotFoundError("Goal not found")
    if is_active and not definition.is_active:
        await _assert_no_other_active(db, definition.goal_type, exclude_id=definition_id)
    if target_value is not None:
        # Also push the new number into the currently-running week's live goal, if
        # one exists for this goal_type — unlike is_active toggles and brand-new
        # definitions (which only take effect next week, via the snapshot
        # get_or_create_current_week takes at week-start), a target_value change is
        # a live recalibration the admin explicitly wants to apply immediately, not
        # wait a week for.
        #
        # Called before mutating `definition`: get_or_create_current_week can
        # perform its own full commit when a week-rollover fires, and if that
        # happened after definition.target_value was already set in-memory,
        # the dirty `definition` could get swept into that unrelated commit
        # instead of being committed together with the AdminActionLog row the
        # router writes afterward.
        current_week = await get_or_create_current_week(db)
        definition.target_value = target_value
        if current_week is not None:
            week_goal = (
                await db.execute(
                    select(BingoWeekGoal).where(
                        BingoWeekGoal.week_id == current_week.id, BingoWeekGoal.goal_type == definition.goal_type
                    )
                )
            ).scalar_one_or_none()
            if week_goal is not None:
                week_goal.target_value = target_value
                db.add(week_goal)
    if is_active is not None:
        definition.is_active = is_active
    db.add(definition)
    await db.flush()
    return definition


async def delete_goal_definition(db: AsyncSession, definition_id: int) -> None:
    definition = await db.get(BingoGoalDefinition, definition_id)
    if definition is None:
        raise NotFoundError("Goal not found")
    await db.delete(definition)
    await db.flush()


async def get_stats_preview(db: AsyncSession) -> list[BingoStatsPreviewItem]:
    """Trailing-7-day totals across ALL players, for every goal type — lets
    an admin see real recent activity before picking a target, so it's
    neither trivially easy nor unreachable. Every metric here (including
    packs_opened) counts only real player-initiated activity — the exact
    same counting rules the live hooks use (e.g. rarity drops and pack opens
    only count real pack opens via CardSource.pack, never admin/task/reward-
    granted cards or bonus pack grants) — so the preview is a fair
    predictor."""
    # Always "the trailing 7 days as of right now", not the currently-running
    # (or most recently completed) BingoWeek's own starts_at/ends_at window —
    # this is meant to help an admin calibrate a target from recent trends
    # before starting a new event, not to retroactively audit one specific
    # past week, so don't expect it to reconcile exactly with any week's own
    # boundaries.
    since = datetime.now(timezone.utc) - WEEK_DURATION

    async def count(stmt) -> int:
        return (await db.execute(stmt)).scalar_one() or 0

    # Real pack opens only: a PackOpening row exists for every pack-creating
    # path (bonus grants, task/collection/league rewards, gifts, the free
    # periodic pack, daily rewards, ...), but only pack_service.open_pack
    # both creates a PackOpening AND rolls cards with CardSource.pack AND
    # fires the live bingo hook — so join through to UserCard/UserCoachCard/
    # UserStadiumCard and filter on that same source, matching the live
    # counter exactly. Each PackOpeningCard row resolves to exactly one of
    # UserCard, UserCoachCard, or UserStadiumCard (roll_and_create_cards's
    # per-slot coach_drop_chance/stadium_drop_chance coin flip — see
    # PackOpeningCard's own CHECK constraint), never more than one, never
    # neither — so this must be an OUTER join to all three sides plus an OR,
    # not a plain inner join to UserCard alone: an opening whose every slot
    # rolled a coach or stadium card has no UserCard rows at all, and an
    # inner join would silently drop it even though it's a real, counter-
    # incrementing open. DISTINCT because a single opening has one
    # PackOpeningCard row per card slot.
    packs_opened = await count(
        select(func.count(func.distinct(PackOpening.id)))
        .join(PackOpeningCard, PackOpeningCard.opening_id == PackOpening.id)
        .outerjoin(UserCard, UserCard.id == PackOpeningCard.user_card_id)
        .outerjoin(UserCoachCard, UserCoachCard.id == PackOpeningCard.user_coach_card_id)
        .outerjoin(UserStadiumCard, UserStadiumCard.id == PackOpeningCard.user_stadium_card_id)
        .where(
            PackOpening.created_at >= since,
            or_(
                UserCard.source == CardSource.pack,
                UserCoachCard.source == CardSource.pack,
                UserStadiumCard.source == CardSource.pack,
                # Skill-token slots carry no card source; a paid opening is
                # the closest equivalent of a real pack purchase.
                and_(PackOpeningCard.skill_code.is_not(None), PackOpening.price_paid > 0),
            ),
        )
    )

    rarity_drop_counts: dict[Rarity, int] = {}
    for rarity in (Rarity.rare, Rarity.epic, Rarity.legendary):
        rarity_drop_counts[rarity] = await count(
            select(func.count(UserCard.id))
            .join(Player, Player.id == UserCard.player_id)
            .where(UserCard.acquired_at >= since, UserCard.source == CardSource.pack, Player.rarity == rarity)
        )

    tactico_matches = await count(
        select(func.count(TacticoMatch.id)).where(
            TacticoMatch.status == TacticoMatchStatus.finished, TacticoMatch.resolved_at >= since
        )
    )
    penalty_matches = await count(
        select(func.count(PenaltyMatch.id)).where(
            PenaltyMatch.status == PenaltyMatchStatus.finished, PenaltyMatch.resolved_at >= since
        )
    )
    arena_matches = await count(
        select(func.count(Match.id)).where(Match.status == MatchStatus.finished, Match.created_at >= since)
    )
    trades_completed = await count(
        select(func.count(TradeOffer.id)).where(
            TradeOffer.status == TradeStatus.accepted, TradeOffer.resolved_at >= since
        )
    )

    counts: dict[BingoGoalType, int] = {
        BingoGoalType.packs_opened: packs_opened,
        BingoGoalType.rare_drops: rarity_drop_counts[Rarity.rare],
        BingoGoalType.epic_drops: rarity_drop_counts[Rarity.epic],
        BingoGoalType.legendary_drops: rarity_drop_counts[Rarity.legendary],
        BingoGoalType.tactico_matches_played: tactico_matches,
        BingoGoalType.penalty_matches_played: penalty_matches,
        BingoGoalType.arena_matches_played: arena_matches,
        BingoGoalType.trades_completed: trades_completed,
    }
    return [BingoStatsPreviewItem(goal_type=t, trailing_7d_count=c) for t, c in counts.items()]
