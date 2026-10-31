from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, local_today
from app.models.card import UserCard
from app.models.enums import CardSource, TaskCategory, TaskConditionType, TradeStatus, TransactionType
from app.models.pack import Pack, PackOpening
from app.models.task import TaskActivity, TaskChestClaim, TaskDefinition, UserTask
from app.models.trade import TradeOffer
from app.models.user import User
from app.models.badge import Badge
from app.schemas.badge import BadgeOut
from app.schemas.pack import PackOpenResult
from app.schemas.task import (
    GrantedSkillTokensOut, TaskChestClaimOut, TaskChestOut, TaskClaimOut, TaskListOut, TaskOut, TaskRerollOut,
    TaskTrackOut,
)
from app.services.telegram_service import check_channel_membership
from app.services.wallet_service import credit_coins, lock_user_for_update

REGULAR_SLOT_COUNT = 5  # the default daily set (GameConfig.task_daily_slots)


async def _assigned_definition_ids(db: AsyncSession, user_id: int) -> set[int]:
    result = await db.execute(select(UserTask.task_definition_id).where(UserTask.user_id == user_id))
    return set(result.scalars().all())


async def _current_metric_value(db: AsyncSession, user: User, metric: Optional[str]) -> int:
    """Current value of a metric_counter metric, used to snapshot a task's
    `metric_baseline` at (re-)assignment time. Every metric a task can use
    (see AdminTasksPage.tsx's hint text) must be handled here — add new ones
    alongside their `evaluate_metric_progress` call site."""
    if metric == "referrals_count":
        return user.referral_count
    if metric == "arena_clean_sheet_wins":
        return user.arena_clean_sheet_wins
    if metric == "memory_levels_completed":
        return user.memory_levels_completed
    if metric == "saboteur_levels_cleared":
        return user.saboteur_levels_cleared
    if metric == "packs_opened":
        return (
            await db.execute(select(func.count(PackOpening.id)).where(PackOpening.user_id == user.id))
        ).scalar_one()
    if metric == "unique_players":
        return (
            await db.execute(
                select(func.count(func.distinct(UserCard.player_id))).where(UserCard.owner_id == user.id)
            )
        ).scalar_one()
    if metric == "trades_completed":
        return (
            await db.execute(
                select(func.count(TradeOffer.id)).where(
                    TradeOffer.status == TradeStatus.accepted, TradeOffer.counts_for_progress.is_(True),
                    or_(TradeOffer.sender_id == user.id, TradeOffer.receiver_id == user.id),
                )
            )
        ).scalar_one()
    return 0


PERIODS = ("daily", "weekly")
# Daily tasks sit in slots 0…, weekly ones from WEEKLY_SLOT_BASE (one slot index space per user).
WEEKLY_SLOT_BASE = 100


def day_key(now: Optional[datetime] = None) -> str:
    return local_today(now).isoformat()


def week_key(now: Optional[datetime] = None) -> str:
    year, week, _ = local_today(now).isocalendar()
    return f"{year}-W{week:02d}"


def _period_key(period: str, now: Optional[datetime] = None) -> str:
    return week_key(now) if period == "weekly" else day_key(now)


def _slots(period: str, config) -> list[int]:
    if period == "weekly":
        return [WEEKLY_SLOT_BASE + i for i in range(max(0, config.task_weekly_slots))]
    return list(range(max(0, config.task_daily_slots)))


async def _assign(db: AsyncSession, user: User, definition: TaskDefinition, slot_index: int, key: str,
                  rows_by_definition: dict[int, UserTask]) -> UserTask:
    """Puts `definition` into `slot_index` for period `key`. The (user,
    definition) row is reused — tasks are a repeatable pool and that pair is
    unique — with its progress and claim reset."""
    baseline = (
        await _current_metric_value(db, user, definition.metric)
        if definition.condition_type == TaskConditionType.metric_counter
        else None
    )
    # A counter task with a zero target has nothing left to do — it's
    # complete the moment it's handed out (progress is only ever
    # re-evaluated when the metric grows, which may never happen).
    completed_at = (
        datetime.now(timezone.utc)
        if definition.condition_type == TaskConditionType.metric_counter and definition.target_value <= 0
        else None
    )
    row = rows_by_definition.get(definition.id)
    if row is None:
        row = UserTask(user_id=user.id, task_definition_id=definition.id)
        rows_by_definition[definition.id] = row
    row.slot_index = slot_index
    row.period_key = key
    row.progress = 0
    row.completed_at = completed_at
    row.reward_claimed = False
    row.metric_baseline = baseline
    db.add(row)
    await db.flush()
    return row


async def _pick(db: AsyncSession, period: str, excluded: set[int]) -> Optional[TaskDefinition]:
    conditions = [
        TaskDefinition.is_active.is_(True), TaskDefinition.category == TaskCategory.regular, TaskDefinition.period == period,
    ]
    if excluded:
        conditions.append(TaskDefinition.id.notin_(excluded))
    return (await db.execute(select(TaskDefinition).where(*conditions).order_by(func.random()).limit(1))).scalar_one_or_none()


async def _ensure_slots_filled(db: AsyncSession, user: User, now: Optional[datetime] = None) -> None:
    """The day's and the week's sets: a slot from an earlier day / week is
    freed (its task leaves, claimed or not), then empty slots get random
    active tasks of that period. A claimed task keeps its slot until the
    period ends — it shows as done, it is not replaced."""
    from app.services.game_config_service import get_config

    config = await get_config(db)
    rows_by_definition = {
        ut.task_definition_id: ut
        for ut in (await db.execute(select(UserTask).where(UserTask.user_id == user.id))).scalars().all()
    }
    definitions = {
        d.id: d for d in (await db.execute(
            select(TaskDefinition).where(TaskDefinition.id.in_(list(rows_by_definition) or [0]))
        )).scalars().all()
    }
    for period in PERIODS:
        key = _period_key(period, now)
        slots = _slots(period, config)
        occupied: set[int] = set()
        excluded: set[int] = set()
        for did, row in rows_by_definition.items():
            definition = definitions.get(did)
            if row.slot_index is None or definition is None or definition.category != TaskCategory.regular:
                continue
            in_period_range = row.slot_index >= WEEKLY_SLOT_BASE if period == "weekly" else row.slot_index < WEEKLY_SLOT_BASE
            if not in_period_range:
                continue
            if row.period_key != key or row.slot_index not in slots:
                row.slot_index = None  # yesterday's / last week's task leaves
                db.add(row)
                continue
            occupied.add(row.slot_index)
            excluded.add(did)
        await db.flush()
        for slot_index in slots:
            if slot_index in occupied:
                continue
            definition = await _pick(db, period, excluded)
            if definition is None:
                break
            definitions[definition.id] = definition
            await _assign(db, user, definition, slot_index, key, rows_by_definition)
            excluded.add(definition.id)


async def _ensure_premium_assigned(db: AsyncSession, user: User) -> None:
    assigned = await _assigned_definition_ids(db, user.id)
    result = await db.execute(
        select(TaskDefinition).where(
            TaskDefinition.is_active.is_(True), TaskDefinition.category == TaskCategory.premium
        )
    )
    for definition in result.scalars().all():
        if definition.id in assigned:
            continue
        db.add(
            UserTask(
                user_id=user.id,
                task_definition_id=definition.id,
                slot_index=None,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.flush()


async def _pack_name(db: AsyncSession, pack_id: Optional[int]) -> Optional[str]:
    if pack_id is None:
        return None
    pack = await db.get(Pack, pack_id)
    return pack.name if pack else None


# «Играть →» by default: where the task's metric / condition is earned.
DEFAULT_ROUTES = {
    "packs_opened": "/packs",
    "unique_players": "/packs",
    "arena_clean_sheet_wins": "/play/arena",
    "memory_levels_completed": "/play/memory",
    "saboteur_levels_cleared": "/play/saboteur",
    "trades_completed": "/trades",
    "referrals_count": "/friends",
    TaskConditionType.match_min_rating.value: "/play/arena",
    TaskConditionType.match_same_country.value: "/play/arena",
    TaskConditionType.penalty_win_max_rating.value: "/play/penalty",
}


def _route(definition: TaskDefinition) -> Optional[str]:
    if definition.category != TaskCategory.regular:
        return None
    if definition.route:
        return definition.route
    if definition.condition_type == TaskConditionType.metric_counter:
        return DEFAULT_ROUTES.get(definition.metric or "")
    return DEFAULT_ROUTES.get(definition.condition_type.value)


async def _to_task_out(db: AsyncSession, user_task: UserTask, definition: TaskDefinition) -> TaskOut:
    regular = definition.category == TaskCategory.regular
    return TaskOut(
        user_task_id=user_task.id,
        code=definition.code,
        name=definition.name,
        description=definition.description,
        category=definition.category,
        reward_coins=definition.reward_coins,
        reward_pack_name=await _pack_name(db, definition.reward_pack_id),
        reward_skill_code=definition.reward_skill_code if definition.reward_skill_tokens > 0 else None,
        reward_skill_tokens=definition.reward_skill_tokens if definition.reward_skill_code else 0,
        channel_username=definition.channel_username,
        invite_link=definition.invite_link,
        progress=user_task.progress,
        target_value=definition.target_value,
        is_completed=user_task.completed_at is not None,
        is_claimed=user_task.reward_claimed,
        period=definition.period if regular else "daily",
        points=definition.points if regular else 0,
        route=_route(definition),
        is_required=definition.is_required and not regular,
    )


def _chests(period: str, config) -> list[dict]:
    raw = config.task_weekly_chests if period == "weekly" else config.task_daily_chests
    return sorted(
        (c for c in (raw or []) if isinstance(c, dict) and int(c.get("points") or 0) > 0),
        key=lambda c: int(c["points"]),
    )


def _resets_at(period: str, now: Optional[datetime] = None) -> datetime:
    today = local_today(now)
    days = 7 - today.weekday() if period == "weekly" else 1
    return datetime.combine(today + timedelta(days=days), time.min, tzinfo=app_timezone())


async def _activity(db: AsyncSession, user_id: int, key: str) -> Optional[TaskActivity]:
    return await db.get(TaskActivity, (user_id, key))


async def _activity_for_update(db: AsyncSession, user_id: int, key: str) -> TaskActivity:
    """The caller holds the user's row lock, so creating the row here can't race."""
    activity = await _activity(db, user_id, key)
    if activity is None:
        activity = TaskActivity(user_id=user_id, period_key=key, points=0, rerolls=0)
        db.add(activity)
        await db.flush()
    return activity


async def _track(db: AsyncSession, user: User, period: str, config, now: Optional[datetime] = None) -> TaskTrackOut:
    key = _period_key(period, now)
    activity = await _activity(db, user.id, key)
    points = activity.points if activity else 0
    claimed = set((await db.execute(
        select(TaskChestClaim.chest_index).where(TaskChestClaim.user_id == user.id, TaskChestClaim.period_key == key)
    )).scalars().all())
    chests = _chests(period, config)
    return TaskTrackOut(
        period_key=key,
        points=points,
        max_points=int(chests[-1]["points"]) if chests else 0,
        chests=[
            TaskChestOut(
                index=i, points=int(c["points"]), coins=int(c.get("coins") or 0), card_rarity=c.get("card_rarity"),
                pack_id=c.get("pack_id"), is_claimed=i in claimed,
                is_available=i not in claimed and points >= int(c["points"]),
            )
            for i, c in enumerate(chests)
        ],
        resets_at=_resets_at(period, now),
    )


async def list_my_tasks(db: AsyncSession, user: User) -> TaskListOut:
    from app.services.game_config_service import get_config

    await _ensure_slots_filled(db, user)
    await _ensure_premium_assigned(db, user)
    await db.commit()

    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(UserTask.user_id == user.id)
    )
    rows = result.all()

    slotted = sorted(
        [(ut, d) for ut, d in rows if ut.slot_index is not None and d.category == TaskCategory.regular],
        key=lambda pair: pair[0].slot_index,
    )
    # Premium tasks aren't slot-rotated like regular ones — once assigned,
    # the UserTask row is permanent, so an admin disabling the definition
    # later must be reflected here too, or the task keeps showing to
    # everyone it was already assigned to.
    premium = sorted(
        [(ut, d) for ut, d in rows if d.category == TaskCategory.premium and d.is_active],
        key=lambda pair: (not pair[1].is_required, pair[1].sort_order, pair[1].id),
    )

    config = await get_config(db)
    activity = await _activity(db, user.id, day_key())
    return TaskListOut(
        regular=[await _to_task_out(db, ut, d) for ut, d in slotted if ut.slot_index < WEEKLY_SLOT_BASE],
        weekly=[await _to_task_out(db, ut, d) for ut, d in slotted if ut.slot_index >= WEEKLY_SLOT_BASE],
        premium=[await _to_task_out(db, ut, d) for ut, d in premium],
        daily_track=await _track(db, user, "daily", config),
        weekly_track=await _track(db, user, "weekly", config),
        rerolls_left=max(0, config.task_free_rerolls - (activity.rerolls if activity else 0)),
        required_badge=await _required_badge(db, config),
    )


async def _required_badge(db: AsyncSession, config) -> Optional[BadgeOut]:
    if not config.task_required_badge_id:
        return None
    badge = await db.get(Badge, config.task_required_badge_id)
    return BadgeOut.model_validate(badge) if badge and badge.is_active else None


async def _grant_required_badge_if_done(db: AsyncSession, user: User) -> Optional[BadgeOut]:
    """«Свой в клубе» once every active required subscription is claimed.
    The bot's sweep takes it back with the coins when one is left."""
    from app.services.game_config_service import get_config
    from app.services.reward_bundle_service import grant_badge

    config = await get_config(db)
    badge = await _required_badge(db, config)
    if badge is None:
        return None
    required = (await db.execute(
        select(TaskDefinition.id).where(
            TaskDefinition.category == TaskCategory.premium, TaskDefinition.is_active.is_(True),
            TaskDefinition.is_required.is_(True),
        )
    )).scalars().all()
    if not required:
        return None
    claimed = (await db.execute(
        select(func.count(UserTask.id)).where(
            UserTask.user_id == user.id, UserTask.task_definition_id.in_(required), UserTask.reward_claimed.is_(True),
        )
    )).scalar_one()
    if claimed < len(required):
        return None
    await grant_badge(db, user, badge.id)
    return badge


async def claim_chest(db: AsyncSession, user: User, period: str, index: int) -> TaskChestClaimOut:
    """Opens activity chest `index` of the current day / week once its
    threshold is reached; the unique (user, period, chest) row makes a
    retried or concurrent request pay only once."""
    from app.services import reward_bundle_service
    from app.services.game_config_service import get_config

    if period not in PERIODS:
        raise NotFoundError("Unknown track")
    config = await get_config(db)
    chests = _chests(period, config)
    if not 0 <= index < len(chests):
        raise NotFoundError("Chest not found")
    chest = chests[index]
    key = _period_key(period)

    locked_user = await lock_user_for_update(db, user.id)
    activity = await _activity(db, locked_user.id, key)
    if (activity.points if activity else 0) < int(chest["points"]):
        raise ConflictError("Сундук ещё закрыт — набери больше очков активности")
    claim = TaskChestClaim(user_id=locked_user.id, period_key=key, chest_index=index)
    try:
        async with db.begin_nested():
            db.add(claim)
            await db.flush()
    except IntegrityError:
        raise ConflictError("Этот сундук уже открыт")

    blocked = locked_user.game_rewards_blocked
    bundle = reward_bundle_service.Bundle(
        coins=0 if blocked else int(chest.get("coins") or 0),
        pack_id=None if blocked else chest.get("pack_id"),
        card_rarity=None if blocked else chest.get("card_rarity"),
    )
    rewards = await reward_bundle_service.grant(
        db, locked_user, bundle, tx_type=TransactionType.task_reward,
        description=f"Сундук активности ({'неделя' if period == 'weekly' else 'день'})",
        card_source=CardSource.task, idempotency_prefix=f"task-chest-{locked_user.id}-{key}-{index}",
        cosmetic_source="task_chest", related_object_type="task_chest_claim", related_object_id=claim.id,
    )
    from app.services import halloween_service

    await halloween_service.grant_chest_pumpkins(db, locked_user, period, key, index)
    await db.commit()
    await db.refresh(locked_user)
    rewards.new_balance = locked_user.balance
    return TaskChestClaimOut(rewards=rewards, new_balance=locked_user.balance)


async def reroll_task(db: AsyncSession, user: User, user_task_id: int) -> TaskRerollOut:
    """Swaps one unfinished task of today's set for another random daily
    task — `task_free_rerolls` times a day."""
    from app.services.game_config_service import get_config

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    user_task = await db.get(UserTask, user_task_id, with_for_update=True)
    if user_task is None:
        raise NotFoundError("Task not found")
    if user_task.user_id != locked_user.id:
        raise ForbiddenError("This task does not belong to you")
    key = day_key()
    if user_task.slot_index is None or user_task.slot_index >= WEEKLY_SLOT_BASE or user_task.period_key != key:
        raise ConflictError("Заменить можно только задание дня")
    if user_task.completed_at is not None:
        raise ConflictError("Выполненное задание не заменяется")
    activity = await _activity_for_update(db, locked_user.id, key)
    if activity.rerolls >= config.task_free_rerolls:
        raise ConflictError("Бесплатные замены на сегодня закончились")

    rows_by_definition = {
        ut.task_definition_id: ut
        for ut in (await db.execute(select(UserTask).where(UserTask.user_id == locked_user.id))).scalars().all()
    }
    excluded = {did for did, ut in rows_by_definition.items() if ut.slot_index is not None}
    definition = await _pick(db, "daily", excluded)
    if definition is None:
        raise ConflictError("Других заданий сейчас нет")
    slot_index = user_task.slot_index
    user_task.slot_index = None
    db.add(user_task)
    await db.flush()
    new_task = await _assign(db, locked_user, definition, slot_index, key, rows_by_definition)
    activity.rerolls += 1
    db.add(activity)
    await db.commit()
    return TaskRerollOut(
        task=await _to_task_out(db, new_task, definition),
        rerolls_left=max(0, config.task_free_rerolls - activity.rerolls),
    )


async def evaluate_metric_progress(db: AsyncSession, user: User, metric: str, value: int) -> None:
    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(
            UserTask.user_id == user.id,
            UserTask.slot_index.isnot(None),
            UserTask.completed_at.is_(None),
            TaskDefinition.condition_type == TaskConditionType.metric_counter,
            TaskDefinition.metric == metric,
        )
    )
    for user_task, definition in result.all():
        # Relative to the value snapshotted when this task instance was
        # (re-)assigned, so a repeated task always needs `target_value` more
        # from that point on, not the player's lifetime total.
        progress = max(0, value - (user_task.metric_baseline or 0))
        user_task.progress = progress
        if progress >= definition.target_value:
            user_task.completed_at = datetime.now(timezone.utc)
        db.add(user_task)


async def evaluate_match_min_rating(db: AsyncSession, user: User, lineup_ratings: list[int]) -> None:
    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(
            UserTask.user_id == user.id,
            UserTask.slot_index.isnot(None),
            UserTask.completed_at.is_(None),
            TaskDefinition.condition_type == TaskConditionType.match_min_rating,
        )
    )
    for user_task, definition in result.all():
        min_rating = (definition.condition_params or {}).get("min_rating", 0)
        if lineup_ratings and all(r >= min_rating for r in lineup_ratings):
            user_task.progress = 1
            user_task.completed_at = datetime.now(timezone.utc)
            db.add(user_task)


async def evaluate_match_same_country(db: AsyncSession, user: User, lineup_countries: list[str]) -> None:
    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(
            UserTask.user_id == user.id,
            UserTask.slot_index.isnot(None),
            UserTask.completed_at.is_(None),
            TaskDefinition.condition_type == TaskConditionType.match_same_country,
        )
    )
    for user_task, _definition in result.all():
        if lineup_countries and len(set(lineup_countries)) == 1:
            user_task.progress = 1
            user_task.completed_at = datetime.now(timezone.utc)
            db.add(user_task)


async def evaluate_penalty_win_max_rating(db: AsyncSession, user: User, player_rating: int, won: bool) -> None:
    if not won:
        return
    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(
            UserTask.user_id == user.id,
            UserTask.slot_index.isnot(None),
            UserTask.completed_at.is_(None),
            TaskDefinition.condition_type == TaskConditionType.penalty_win_max_rating,
        )
    )
    for user_task, definition in result.all():
        max_rating = (definition.condition_params or {}).get("max_rating", 0)
        if player_rating < max_rating:
            user_task.progress = 1
            user_task.completed_at = datetime.now(timezone.utc)
            db.add(user_task)


PREMIUM_TASK_BACKFILL_COINS = 1000


async def backfill_premium_task_coins(db: AsyncSession) -> tuple[int, int]:
    """One-off, idempotent action for premium (channel-subscription) tasks
    that predate coin rewards: sets `reward_coins=1000` on active premium
    definitions still at 0, then retroactively credits that amount to users
    who'd already claimed one of those tasks for 0 coins. Safe to call more
    than once — the second call finds no definitions at `reward_coins=0` and
    no claims with `reward_coins_granted IS NULL` left to touch."""
    definitions_result = await db.execute(
        select(TaskDefinition).where(
            TaskDefinition.category == TaskCategory.premium,
            TaskDefinition.is_active.is_(True),
            TaskDefinition.reward_coins == 0,
            or_(TaskDefinition.channel_username.is_not(None), TaskDefinition.channel_chat_id.is_not(None)),
        )
    )
    definitions = definitions_result.scalars().all()
    for definition in definitions:
        definition.reward_coins = PREMIUM_TASK_BACKFILL_COINS
        db.add(definition)
    await db.flush()

    definition_ids = [d.id for d in definitions]
    if not definition_ids:
        await db.commit()
        return 0, 0

    claims_result = await db.execute(
        select(UserTask)
        .where(
            UserTask.task_definition_id.in_(definition_ids),
            UserTask.reward_claimed.is_(True),
            UserTask.reward_coins_granted.is_(None),
        )
        .with_for_update()
    )
    claims = claims_result.scalars().all()
    credited_users = 0
    for user_task in claims:
        claimed_user = await lock_user_for_update(db, user_task.user_id)
        await credit_coins(
            db, claimed_user, PREMIUM_TASK_BACKFILL_COINS, TransactionType.premium_subscription_adjustment,
            "Ретроактивное начисление за премиум-задание", "user_task", user_task.id,
        )
        user_task.reward_coins_granted = PREMIUM_TASK_BACKFILL_COINS
        db.add(user_task)
        credited_users += 1

    await db.commit()
    return len(definitions), credited_users


async def claim_task_reward(db: AsyncSession, user: User, user_task_id: int) -> TaskClaimOut:
    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(UserTask.id == user_task_id)
    )
    row = result.first()
    if row is None:
        raise NotFoundError("Task not found")
    user_task, definition = row
    if user_task.user_id != user.id:
        raise ForbiddenError("This task does not belong to you")
    if user_task.completed_at is None:
        raise ConflictError("This task is not completed yet")
    if user_task.reward_claimed:
        raise ConflictError("Reward for this task has already been claimed")

    if definition.category == TaskCategory.premium and (definition.channel_chat_id or definition.channel_username):
        # Private channels with no public @username can only be checked by
        # numeric chat id — getChatMember has no way to resolve an invite link.
        chat_id = definition.channel_chat_id or definition.channel_username
        is_member = await check_channel_membership(user.telegram_id, chat_id)
        if not is_member:
            raise ConflictError("Похоже, ты ещё не подписан на канал", details={"channel_username": definition.channel_username})

    locked_user = await lock_user_for_update(db, user.id)
    # Re-read the task under a row lock so a concurrent claim on the same
    # task can't race past the reward_claimed check before either commits.
    await db.refresh(user_task, with_for_update=True)
    if user_task.reward_claimed:
        raise ConflictError("Reward for this task has already been claimed")

    reward_coins = 0 if locked_user.game_rewards_blocked else definition.reward_coins
    user_task.reward_coins_granted = reward_coins
    if reward_coins > 0:
        await credit_coins(
            db, locked_user, reward_coins, TransactionType.task_reward,
            f"Задание «{definition.name}»", "user_task", user_task.id,
        )

    granted_pack: Optional[PackOpenResult] = None
    if definition.reward_pack_id and not locked_user.game_rewards_blocked:
        # Deferred: pack_service imports task_service at module level (for
        # track_pack_opened_tasks), so a top-level import here would be circular.
        from app.services.collection_service import grant_collection_rewards_for_new_cards
        from app.services.pack_service import grant_bonus_pack_opening

        granted_pack = await grant_bonus_pack_opening(
            db, locked_user, definition.reward_pack_id,
            idempotency_prefix=f"task-reward-{locked_user.id}-{definition.reward_pack_id}",
        )
        if granted_pack is not None:
            granted_pack.collection_rewards = await grant_collection_rewards_for_new_cards(
                db, locked_user, [item.card.player.id for item in granted_pack.cards]
            )

    granted_tokens: Optional[GrantedSkillTokensOut] = None
    if definition.reward_skill_code and definition.reward_skill_tokens > 0 and not locked_user.game_rewards_blocked:
        # Same transaction and same user_task row lock as the coin reward
        # above, so a concurrent/retried claim cannot grant tokens twice.
        from app.services.card_skill_service import grant_tokens

        await grant_tokens(
            db, locked_user, definition.reward_skill_code, definition.reward_skill_tokens, "grant_task",
            related_object_type="user_task", related_object_id=user_task.id, reason=f"Задание «{definition.name}»",
        )
        granted_tokens = GrantedSkillTokensOut(
            skill_code=definition.reward_skill_code, quantity=definition.reward_skill_tokens,
        )

    user_task.reward_claimed = True
    points_added = 0
    if definition.category == TaskCategory.regular and user_task.slot_index is not None and user_task.period_key:
        # The task stays in its slot as done until its day / week ends; its
        # points go to that period's activity track (the chests).
        activity = await _activity_for_update(db, locked_user.id, user_task.period_key)
        activity.points += definition.points
        db.add(activity)
        points_added = definition.points
        from app.services import halloween_service

        await halloween_service.grant_task_pumpkins(db, locked_user, user_task.id, user_task.period_key)

    granted_badge: Optional[BadgeOut] = None
    if definition.category == TaskCategory.premium and definition.is_required and not locked_user.game_rewards_blocked:
        db.add(user_task)
        await db.flush()
        granted_badge = await _grant_required_badge_if_done(db, locked_user)

    db.add(user_task)
    await db.commit()
    await db.refresh(locked_user)

    if granted_pack is not None:
        granted_pack.new_balance = locked_user.balance

    return TaskClaimOut(
        reward_coins=reward_coins,
        new_balance=locked_user.balance,
        granted_pack=granted_pack,
        granted_skill_tokens=granted_tokens,
        points_added=points_added,
        granted_badge=granted_badge,
    )
