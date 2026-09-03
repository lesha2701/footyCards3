from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.bingo import BingoGoalDefinition, BingoState, BingoWeek, BingoWeekGoal, BingoWeekReward
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
from app.models.pack import PackOpening
from app.models.penalty import PenaltyMatch
from app.models.player import Player
from app.models.tactico import TacticoMatch
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.bingo import BingoClaimResult, BingoCurrentOut, BingoGoalOut, BingoStatsPreviewItem
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

WEEK_DURATION = timedelta(days=7)


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
        definition.target_value = target_value
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
    neither trivially easy nor unreachable. Uses the exact same counting
    rules the live hooks use (e.g. rarity drops only count real pack opens,
    not admin-granted cards) so the preview is a fair predictor."""
    since = datetime.now(timezone.utc) - WEEK_DURATION

    async def count(stmt) -> int:
        return (await db.execute(stmt)).scalar_one() or 0

    packs_opened = await count(select(func.count(PackOpening.id)).where(PackOpening.created_at >= since))

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
