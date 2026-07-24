import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import SaboteurClaimOut, SaboteurRevealOut, SaboteurStartOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

GRID_SIZE = 16


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


async def start_session(db: AsyncSession, user: User, bomb_count: int = 1) -> SaboteurStartOut:
    config = await get_config(db)
    if not (1 <= bomb_count <= config.saboteur_max_bomb_count):
        raise ConflictError(
            f"bomb_count must be between 1 and {config.saboteur_max_bomb_count}",
            details={"max_bomb_count": config.saboteur_max_bomb_count},
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
    if locked_user.saboteur_rewarded_attempts_today >= config.saboteur_daily_limit:
        raise ConflictError(
            "Daily reward attempts for Saboteur exhausted; you can still play unrewarded",
            details={"daily_limit": config.saboteur_daily_limit},
        )

    bomb_indices = random.sample(range(GRID_SIZE), bomb_count)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.saboteur, status=GameSessionStatus.in_progress,
        server_state={"bomb_indices": bomb_indices, "bomb_count": bomb_count, "revealed": []},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SaboteurStartOut(session_id=session.id, grid_size=GRID_SIZE, bomb_count=bomb_count)


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
    if not (0 <= cell_index < GRID_SIZE):
        raise ConflictError("Invalid cell index")

    state = dict(session.server_state)
    revealed = list(state["revealed"])
    if cell_index in revealed:
        raise ConflictError("Cell already revealed")

    if cell_index in state["bomb_indices"]:
        revealed.append(cell_index)
        state["revealed"] = revealed
        session.server_state = state
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = session.score // 2
        db.add(session)
        await db.commit()
        return SaboteurRevealOut(
            is_bomb=True, session_id=session.id, score=session.score, status=session.status.value,
            reward_coins=session.reward_coins,
        )

    revealed.append(cell_index)
    state["revealed"] = revealed
    session.server_state = state
    session.score += config.saboteur_cell_reward * state["bomb_count"]
    db.add(session)
    await db.commit()
    return SaboteurRevealOut(is_bomb=False, session_id=session.id, score=session.score, status=session.status.value)


async def end_session(db: AsyncSession, user: User, session_id: int) -> SaboteurRevealOut:
    """Lets the player voluntarily stop and bank the current score."""
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = session.score
    db.add(session)
    await db.commit()
    return SaboteurRevealOut(
        is_bomb=False, session_id=session.id, score=session.score, status=session.status.value,
        reward_coins=session.reward_coins,
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
    if locked_user.saboteur_rewarded_attempts_today >= config.saboteur_daily_limit:
        raise ConflictError("Daily reward attempts for Saboteur exhausted")

    reward = 0 if locked_user.game_rewards_blocked else session.reward_coins
    session.is_rewarded = True
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
