"""«Ферги Тайм» (docs/match-3d.md): the match runs on the phone. The server
records that it was played to the end and pays a flat fee for it
(GameConfig.fergie_match_coins, up to fergie_daily_limit a day), the same for a
win and a defeat.

The score stays on the client: nothing here replays the match, so nothing may
depend on it. What the server does know is the clock: a match can't be over
sooner than `MIN_SECONDS` after its start. The usual counters: the shared hourly
cap of matches and a daily cap of rewarded ones; past it the match still counts
for tasks, it just pays nothing.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import FergieFinishOut, FergieStartOut
from app.services.club_pass_service import extra_rewarded_attempts
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

# lib/match3d MATCH_SECONDS is 200 of game time, which the screen plays at 0.85.
MIN_SECONDS = 150


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.fergie_attempts_reset_at) if user.fergie_attempts_reset_at else None
    if reset_day != today:
        user.fergie_rewarded_attempts_today = 0
        user.fergie_attempts_reset_at = _now()
        db.add(user)


def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    now = _now()
    started = user.fergie_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.fergie_hourly_attempts = 0
        user.fergie_hour_started_at = now
    if user.fergie_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (now - ensure_aware(user.fergie_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    user.fergie_hourly_attempts += 1
    db.add(user)


async def start(db: AsyncSession, user: User) -> FergieStartOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    _take_hourly_attempt(db, locked, config.hourly_game_limit)
    _ensure_daily_reset(db, locked)
    # Walked out of the last one: it stays unplayed.
    await db.execute(
        update(GameSession)
        .where(
            GameSession.user_id == locked.id, GameSession.game_type == GameType.fergie_time,
            GameSession.status == GameSessionStatus.in_progress,
        )
        .values(status=GameSessionStatus.expired)
    )
    session = GameSession(user_id=locked.id, game_type=GameType.fergie_time, status=GameSessionStatus.in_progress)
    db.add(session)
    await db.commit()
    return FergieStartOut(session_id=session.id)


async def finish(db: AsyncSession, user: User, session_id: int) -> FergieFinishOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    session = (await db.execute(
        select(GameSession)
        .where(GameSession.id == session_id, GameSession.user_id == locked.id, GameSession.game_type == GameType.fergie_time)
        .with_for_update()
    )).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Матч не найден")
    if session.status == GameSessionStatus.won:
        # A retried request: what the first one paid, nothing more.
        await db.commit()
        return FergieFinishOut(reward_coins=session.reward_coins, new_balance=locked.balance, daily_cap_reached=session.reward_coins == 0)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("Этот матч уже не идёт")
    if _now() - ensure_aware(session.created_at) < timedelta(seconds=MIN_SECONDS):
        raise ConflictError("Матч ещё не мог закончиться")

    _ensure_daily_reset(db, locked)
    cap = config.fergie_daily_limit + await extra_rewarded_attempts(db, locked.id, config)
    capped = locked.fergie_rewarded_attempts_today >= cap
    reward = 0 if capped or locked.game_rewards_blocked else config.fergie_match_coins
    if not capped:
        locked.fergie_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, locked, reward, TransactionType.game_reward,
            "Награда за Ферги Тайм", related_object_type="game_session", related_object_id=session.id,
        )
    # «won» is the only finished status a played match has here: it says the
    # game was played out, not who won it.
    session.status = GameSessionStatus.won
    session.finished_at = _now()
    session.reward_coins = reward
    session.is_rewarded = True
    db.add(session)
    db.add(locked)
    await db.commit()
    await db.refresh(locked)
    return FergieFinishOut(reward_coins=reward, new_balance=locked.balance, daily_cap_reached=capped)
