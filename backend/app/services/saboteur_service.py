import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import SaboteurClaimOut, SaboteurRevealOut, SaboteurStartOut
from app.services import task_service
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

LINE_SIZE = 5


def _line_reward(base_reward: int, steward_count: int, growth: float, level: int) -> int:
    """Reward for clearing a given ladder level: scales with how many
    stewards are on the line (harder pick) and compounds by `growth` per
    level climbed, so pressing on gets progressively more lucrative."""
    return round(base_reward * steward_count * (growth ** (level - 1)))


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.saboteur_attempts_reset_at) if user.saboteur_attempts_reset_at else None
    if reset_day != today:
        user.saboteur_rewarded_attempts_today = 0
        user.saboteur_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.saboteur_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.saboteur_hourly_attempts = 0
        user.saboteur_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User, steward_count: int = 1) -> SaboteurStartOut:
    config = await get_config(db)
    if not (1 <= steward_count <= config.saboteur_max_steward_count):
        raise ConflictError(
            f"steward_count must be between 1 and {config.saboteur_max_steward_count}",
            details={"max_steward_count": config.saboteur_max_steward_count},
        )

    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.saboteur_hourly_attempts >= config.hourly_game_limit:
        now = datetime.now(timezone.utc)
        remaining = timedelta(hours=1) - (now - ensure_aware(locked_user.saboteur_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.saboteur_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    line_stewards = random.sample(range(LINE_SIZE), steward_count)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.saboteur, status=GameSessionStatus.in_progress,
        server_state={"steward_count": steward_count, "level": 1, "line_stewards": line_stewards},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SaboteurStartOut(session_id=session.id, line_size=LINE_SIZE, steward_count=steward_count, level=1)


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.saboteur:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def reveal_cell(db: AsyncSession, user: User, session_id: int, cell_index: int) -> SaboteurRevealOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    if not (0 <= cell_index < LINE_SIZE):
        raise ConflictError("Invalid cell index")

    state = dict(session.server_state)
    steward_count = state["steward_count"]
    level = state["level"]
    line_stewards = state["line_stewards"]
    growth = float(config.saboteur_line_growth)

    if cell_index in line_stewards:
        # Softer failure than an outright wipe: the fan still gets stopped,
        # but always walks away with at least what clearing one line is
        # worth, regardless of how far up the ladder they'd climbed.
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = _line_reward(config.saboteur_line_base_reward, steward_count, growth, 1)
        db.add(session)
        await db.commit()
        return SaboteurRevealOut(
            is_steward=True, session_id=session.id, score=session.score, level=level,
            status=session.status.value, reward_coins=session.reward_coins,
        )

    reward = _line_reward(config.saboteur_line_base_reward, steward_count, growth, level)
    session.score += reward
    next_level = level + 1
    state["level"] = next_level
    state["line_stewards"] = random.sample(range(LINE_SIZE), steward_count)

    locked_user = await lock_user_for_update(db, user.id)
    locked_user.saboteur_levels_cleared += 1
    db.add(locked_user)
    await task_service.evaluate_metric_progress(
        db, locked_user, "saboteur_levels_cleared", locked_user.saboteur_levels_cleared
    )
    session.server_state = state
    db.add(session)
    await db.commit()
    return SaboteurRevealOut(
        is_steward=False, session_id=session.id, score=session.score, level=next_level,
        status=session.status.value,
    )


async def end_session(db: AsyncSession, user: User, session_id: int) -> SaboteurRevealOut:
    """Lets the player voluntarily stop and bank the current score."""
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    state = session.server_state
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = session.score
    db.add(session)
    await db.commit()
    return SaboteurRevealOut(
        is_steward=False, session_id=session.id, score=session.score, level=state["level"],
        status=session.status.value, reward_coins=session.reward_coins,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> SaboteurClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.saboteur_rewarded_attempts_today >= config.saboteur_daily_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.saboteur_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Футбольный сапёр", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return SaboteurClaimOut(reward_coins=reward, new_balance=locked_user.balance)
