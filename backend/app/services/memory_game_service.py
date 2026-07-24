import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession, MemoryGameRound
from app.models.user import User
from app.schemas.game import MemoryClaimOut, MemoryLeaderboardEntry, MemoryStartOut, MemorySubmitOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

SYMBOLS = ["⚽", "🥅", "🟨", "🟥", "👟", "🧤", "🏆", "🚩", "🎯", "🔥"]
INITIAL_LENGTH = 3


def _generate_sequence(length: int) -> list[str]:
    return [random.choice(SYMBOLS) for _ in range(length)]


def _reveal_ms(round_number: int) -> int:
    return max(1200, 1000 + round_number * 400)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.memory_attempts_reset_at) if user.memory_attempts_reset_at else None
    if reset_day != today:
        user.memory_rewarded_attempts_today = 0
        user.memory_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.memory_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.memory_hourly_attempts = 0
        user.memory_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> MemoryStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.memory_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.memory_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.memory_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)
    if locked_user.memory_rewarded_attempts_today >= config.memory_daily_reward_limit:
        raise ConflictError(
            "Daily reward attempts for Memory Sequence exhausted; you can still play unrewarded",
            details={"daily_limit": config.memory_daily_reward_limit},
        )

    session = GameSession(user_id=locked_user.id, game_type=GameType.memory_sequence, status=GameSessionStatus.in_progress)
    db.add(session)
    await db.flush()

    sequence = _generate_sequence(INITIAL_LENGTH)
    round_ = MemoryGameRound(session_id=session.id, round_number=1, sequence=",".join(sequence))
    db.add(round_)
    await db.commit()

    return MemoryStartOut(session_id=session.id, round_number=1, sequence=sequence, reveal_ms=_reveal_ms(1))


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.memory_sequence:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def submit_round(db: AsyncSession, user: User, session_id: int, answer: list[str]) -> MemorySubmitOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    result = await db.execute(
        select(MemoryGameRound)
        .where(MemoryGameRound.session_id == session.id)
        .order_by(MemoryGameRound.round_number.desc())
        .limit(1)
    )
    current_round = result.scalar_one()
    expected = current_round.sequence.split(",")
    correct = answer == expected
    current_round.was_correct = correct

    if not correct:
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = min(session.score, config.memory_reward_cap)
        await db.commit()
        return MemorySubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)

    session.score += current_round.round_number * 10
    next_round_number = current_round.round_number + 1
    next_sequence = _generate_sequence(INITIAL_LENGTH + next_round_number - 1)
    next_round = MemoryGameRound(session_id=session.id, round_number=next_round_number, sequence=",".join(next_sequence))
    db.add(next_round)
    await db.commit()

    return MemorySubmitOut(
        correct=True,
        session_id=session.id,
        score=session.score,
        status=session.status.value,
        next_round=MemoryStartOut(
            session_id=session.id,
            round_number=next_round_number,
            sequence=next_sequence,
            reveal_ms=_reveal_ms(next_round_number),
        ),
    )


async def end_session(db: AsyncSession, user: User, session_id: int) -> MemorySubmitOut:
    """Lets the player voluntarily stop and bank the current score."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    session.status = GameSessionStatus.lost
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = min(session.score, config.memory_reward_cap)
    await db.commit()
    return MemorySubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> MemoryClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    # Re-read the session under a row lock so a concurrent claim on the same
    # session can't race past this check before either commits.
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    if locked_user.memory_rewarded_attempts_today >= config.memory_daily_reward_limit:
        raise ConflictError("Daily reward attempts for Memory Sequence exhausted")

    reward = 0 if locked_user.game_rewards_blocked else min(session.score, config.memory_reward_cap)
    session.is_rewarded = True
    session.status = GameSessionStatus.rewarded
    locked_user.memory_rewarded_attempts_today += 1

    new_best = False
    if session.score > locked_user.memory_best_score:
        locked_user.memory_best_score = session.score
        new_best = True

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Memory Sequence", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return MemoryClaimOut(
        reward_coins=reward, new_balance=locked_user.balance, new_best_score=new_best, best_score=locked_user.memory_best_score
    )


async def leaderboard(db: AsyncSession, limit: int = 20) -> list[MemoryLeaderboardEntry]:
    result = await db.execute(
        select(User).where(User.memory_best_score > 0).order_by(User.memory_best_score.desc()).limit(limit)
    )
    users = result.scalars().all()
    return [
        MemoryLeaderboardEntry(
            user_id=u.id, display_name=u.full_display_name(), avatar_url=u.avatar_url, best_score=u.memory_best_score
        )
        for u in users
    ]
