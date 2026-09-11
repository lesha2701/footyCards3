from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import ensure_aware
from app.models.game_config import GameConfig
from app.models.user import User


def _ensure_hourly_reset(user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.club_games_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.club_games_hourly_attempts = 0
        user.club_games_hour_started_at = now


async def consume_club_game_slot(db: AsyncSession, locked_user: User, config: GameConfig) -> None:
    """Shared hourly pool across every club-scoped mini-game (Повтори порядок,
    Пенальти, Своя позиция): a member gets `club_games_hourly_limit` plays per
    hour TOTAL, spendable on any mix of these games — not that many plays of
    each independently. Caller must already hold the row lock on `locked_user`
    (via wallet_service.lock_user_for_update) and commit afterward."""
    _ensure_hourly_reset(locked_user)
    if locked_user.club_games_hourly_attempts >= config.club_games_hourly_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.club_games_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for club games",
            details={
                "hourly_limit": config.club_games_hourly_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.club_games_hourly_attempts += 1
    db.add(locked_user)
