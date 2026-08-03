from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import TaskCategory, TaskConditionType, TransactionType
from app.models.pack import Pack
from app.models.task import TaskDefinition, UserTask
from app.models.user import User
from app.schemas.pack import PackOpenResult
from app.schemas.task import TaskClaimOut, TaskListOut, TaskOut
from app.services.telegram_service import check_channel_membership
from app.services.wallet_service import credit_coins, lock_user_for_update

REGULAR_SLOT_COUNT = 5


async def _assigned_definition_ids(db: AsyncSession, user_id: int) -> set[int]:
    result = await db.execute(select(UserTask.task_definition_id).where(UserTask.user_id == user_id))
    return set(result.scalars().all())


async def _ensure_slots_filled(db: AsyncSession, user: User) -> None:
    occupied_result = await db.execute(
        select(UserTask.slot_index).where(UserTask.user_id == user.id, UserTask.slot_index.isnot(None))
    )
    occupied = set(occupied_result.scalars().all())
    empty_slots = [i for i in range(REGULAR_SLOT_COUNT) if i not in occupied]
    if not empty_slots:
        return

    excluded = await _assigned_definition_ids(db, user.id)
    for slot_index in empty_slots:
        conditions = [TaskDefinition.is_active.is_(True), TaskDefinition.category == TaskCategory.regular]
        if excluded:
            conditions.append(TaskDefinition.id.notin_(excluded))
        result = await db.execute(select(TaskDefinition).where(*conditions).order_by(func.random()).limit(1))
        definition = result.scalar_one_or_none()
        if definition is None:
            continue
        db.add(UserTask(user_id=user.id, task_definition_id=definition.id, slot_index=slot_index))
        await db.flush()
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


async def _to_task_out(db: AsyncSession, user_task: UserTask, definition: TaskDefinition) -> TaskOut:
    return TaskOut(
        user_task_id=user_task.id,
        code=definition.code,
        name=definition.name,
        description=definition.description,
        category=definition.category,
        reward_coins=definition.reward_coins,
        reward_pack_name=await _pack_name(db, definition.reward_pack_id),
        channel_username=definition.channel_username,
        invite_link=definition.invite_link,
        progress=user_task.progress,
        target_value=definition.target_value,
        is_completed=user_task.completed_at is not None,
        is_claimed=user_task.reward_claimed,
    )


async def list_my_tasks(db: AsyncSession, user: User) -> TaskListOut:
    await _ensure_slots_filled(db, user)
    await _ensure_premium_assigned(db, user)
    await db.commit()

    result = await db.execute(
        select(UserTask, TaskDefinition)
        .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
        .where(UserTask.user_id == user.id)
    )
    rows = result.all()

    regular = sorted(
        [(ut, d) for ut, d in rows if ut.slot_index is not None],
        key=lambda pair: pair[0].slot_index,
    )
    premium = [(ut, d) for ut, d in rows if d.category == TaskCategory.premium]

    return TaskListOut(
        regular=[await _to_task_out(db, ut, d) for ut, d in regular],
        premium=[await _to_task_out(db, ut, d) for ut, d in premium],
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
        user_task.progress = value
        if value >= definition.target_value:
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
            raise ConflictError("not_subscribed", details={"channel_username": definition.channel_username})

    locked_user = await lock_user_for_update(db, user.id)
    # Re-read the task under a row lock so a concurrent claim on the same
    # task can't race past the reward_claimed check before either commits.
    await db.refresh(user_task, with_for_update=True)
    if user_task.reward_claimed:
        raise ConflictError("Reward for this task has already been claimed")

    reward_coins = 0 if locked_user.game_rewards_blocked else definition.reward_coins
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

    user_task.reward_claimed = True
    refilled_task_out: Optional[TaskOut] = None
    if definition.category == TaskCategory.regular:
        freed_slot_index = user_task.slot_index
        user_task.slot_index = None
        db.add(user_task)
        await db.flush()
        await _ensure_slots_filled(db, locked_user)
        await db.flush()
        new_slot_result = await db.execute(
            select(UserTask, TaskDefinition)
            .join(TaskDefinition, TaskDefinition.id == UserTask.task_definition_id)
            .where(UserTask.user_id == locked_user.id, UserTask.slot_index == freed_slot_index)
        )
        new_row = new_slot_result.first()
        if new_row is not None:
            new_user_task, new_definition = new_row
            refilled_task_out = await _to_task_out(db, new_user_task, new_definition)

    db.add(user_task)
    await db.commit()
    await db.refresh(locked_user)

    if granted_pack is not None:
        granted_pack.new_balance = locked_user.balance

    return TaskClaimOut(
        reward_coins=reward_coins,
        new_balance=locked_user.balance,
        granted_pack=granted_pack,
        refilled_task=refilled_task_out,
    )
