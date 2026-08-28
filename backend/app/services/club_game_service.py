import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.club import Club
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, GameType
from app.models.game import GameSession, MemoryGameRound
from app.models.user import User
from app.schemas.club_game import ClubGameClaimOut, ClubGameStartOut, ClubGameSubmitOut
from app.services.club_budget_service import credit_club_budget
from app.services.club_service import _lock_club, _require_membership
from app.services.game_config_service import get_config
from app.services.wallet_service import lock_user_for_update

# Fixed row of 5 icons — positions never change, only the highlighted order
# does. Values are opaque IDs shared with the frontend's icon row, the same
# way memory_game_service.SYMBOLS are shared with MemoryGamePage.
ICONS = ["⚽", "🥅", "🟨", "🟥", "🏆"]
INITIAL_LENGTH = 3
ANSWER_TIMEOUT_MS = 15000


def _generate_sequence(length: int) -> list[str]:
    return [random.choice(ICONS) for _ in range(length)]


def _reveal_ms(round_number: int) -> int:
    return max(1200, 1000 + round_number * 400)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.club_game_attempts_reset_at) if user.club_game_attempts_reset_at else None
    if reset_day != today:
        user.club_game_rewarded_attempts_today = 0
        user.club_game_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.club_game_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.club_game_hourly_attempts = 0
        user.club_game_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> ClubGameStartOut:
    membership = await _require_membership(db, user.id)
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.club_game_hourly_attempts >= config.club_game_hourly_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.club_game_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.club_game_hourly_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.club_game_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.club_sequence, status=GameSessionStatus.in_progress,
        server_state={"club_id": membership.club_id},
    )
    db.add(session)
    await db.flush()

    sequence = _generate_sequence(INITIAL_LENGTH)
    round_ = MemoryGameRound(session_id=session.id, round_number=1, sequence=",".join(sequence))
    db.add(round_)
    await db.commit()

    return ClubGameStartOut(
        session_id=session.id, round_number=1, icons=ICONS, sequence=sequence, reveal_ms=_reveal_ms(1),
        answer_timeout_ms=ANSWER_TIMEOUT_MS,
    )


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.club_sequence:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def submit_round(db: AsyncSession, user: User, session_id: int, answer: list[str]) -> ClubGameSubmitOut:
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
        session.reward_coins = min(session.score, config.club_game_reward_cap)
        await db.commit()
        return ClubGameSubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)

    session.score += current_round.round_number * 10
    next_round_number = current_round.round_number + 1
    next_sequence = _generate_sequence(INITIAL_LENGTH + next_round_number - 1)
    next_round = MemoryGameRound(session_id=session.id, round_number=next_round_number, sequence=",".join(next_sequence))
    db.add(next_round)

    await db.commit()

    return ClubGameSubmitOut(
        correct=True,
        session_id=session.id,
        score=session.score,
        status=session.status.value,
        next_round=ClubGameStartOut(
            session_id=session.id,
            round_number=next_round_number,
            icons=ICONS,
            sequence=next_sequence,
            reveal_ms=_reveal_ms(next_round_number),
            answer_timeout_ms=ANSWER_TIMEOUT_MS,
        ),
    )


async def end_session(db: AsyncSession, user: User, session_id: int) -> ClubGameSubmitOut:
    """Lets the player voluntarily stop and bank the current score."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    session.status = GameSessionStatus.lost
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = min(session.score, config.club_game_reward_cap)
    await db.commit()
    return ClubGameSubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> ClubGameClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    # Re-read the session under a row lock so a concurrent claim on the same
    # session can't race past this check before either commits — same
    # reasoning as memory_game_service.claim_reward.
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.club_game_rewarded_attempts_today >= config.club_game_daily_reward_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else min(session.score, config.club_game_reward_cap)
    session.is_rewarded = True
    session.status = GameSessionStatus.rewarded
    if not daily_cap_reached:
        locked_user.club_game_rewarded_attempts_today += 1
    db.add(locked_user)
    db.add(session)

    club_id = (session.server_state or {}).get("club_id")
    new_budget = None
    if reward > 0 and club_id is not None:
        club = await _lock_club(db, club_id)
        if club is not None and not club.is_disbanded:
            await credit_club_budget(
                db, club, reward, ClubBudgetTransactionType.club_game_reward,
                f"Клубная игра: {user.username or user.first_name or f'#{user.id}'}",
                related_object_type="game_session", related_object_id=session.id,
            )
            new_budget = club.budget
        else:
            reward = 0

    await db.commit()

    if new_budget is None and club_id is not None:
        club = await db.get(Club, club_id)
        new_budget = club.budget if club is not None else 0

    return ClubGameClaimOut(reward_coins=reward, new_club_budget=new_budget or 0)
