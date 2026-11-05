"""«Ферги Тайм» (docs/match-3d.md): the match runs on the phone and pays nothing
itself. The server only records that one was played to the end, for the tasks
and the «Путь дебютанта» to count.

The score stays on the client: nothing here replays the match, so nothing may
depend on it. What the server does know is the clock, and a match can't be over
sooner than `MIN_SECONDS` after its start. That, and a task paying once a day or
a week, is what stands between a script and the task's coins, so the mode needs
no hourly / daily counters until it pays by itself.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import GameSessionStatus, GameType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import FergieFinishOut, FergieStartOut

# lib/match3d MATCH_SECONDS is 200 of game time, which the screen plays at 0.85.
MIN_SECONDS = 150


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def start(db: AsyncSession, user: User) -> FergieStartOut:
    # Walked out of the last one: it stays unplayed.
    await db.execute(
        update(GameSession)
        .where(
            GameSession.user_id == user.id, GameSession.game_type == GameType.fergie_time,
            GameSession.status == GameSessionStatus.in_progress,
        )
        .values(status=GameSessionStatus.expired)
    )
    session = GameSession(user_id=user.id, game_type=GameType.fergie_time, status=GameSessionStatus.in_progress)
    db.add(session)
    await db.commit()
    return FergieStartOut(session_id=session.id)


async def finish(db: AsyncSession, user: User, session_id: int) -> FergieFinishOut:
    session = (await db.execute(
        select(GameSession)
        .where(GameSession.id == session_id, GameSession.user_id == user.id, GameSession.game_type == GameType.fergie_time)
        .with_for_update()
    )).scalar_one_or_none()
    if session is None:
        raise NotFoundError("Матч не найден")
    if session.status == GameSessionStatus.won:
        return FergieFinishOut(finished=True)  # a retried request
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("Этот матч уже не идёт")
    if _now() - ensure_aware(session.created_at) < timedelta(seconds=MIN_SECONDS):
        raise ConflictError("Матч ещё не мог закончиться")
    # «won» is the only finished status a played match has here: it says the
    # game was played out, not who won it.
    session.status = GameSessionStatus.won
    session.finished_at = _now()
    await db.commit()
    return FergieFinishOut(finished=True)
