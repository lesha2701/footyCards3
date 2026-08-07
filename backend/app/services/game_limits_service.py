from datetime import datetime, timedelta, timezone

from app.core.timeutil import ensure_aware
from app.models.game_config import GameConfig
from app.models.user import User
from app.schemas.game import GameLimitsOut


def _remaining(hourly_attempts: int, hour_started_at, limit: int) -> int:
    now = datetime.now(timezone.utc)
    if hour_started_at is None or now - ensure_aware(hour_started_at) >= timedelta(hours=1):
        return limit
    return max(0, limit - hourly_attempts)


def get_remaining_plays(user: User, config: GameConfig) -> GameLimitsOut:
    limit = config.hourly_game_limit
    return GameLimitsOut(
        hourly_limit=limit,
        memory=_remaining(user.memory_hourly_attempts, user.memory_hour_started_at, limit),
        arena=_remaining(user.match_hourly_attempts, user.match_hour_started_at, limit),
        saboteur=_remaining(user.saboteur_hourly_attempts, user.saboteur_hour_started_at, limit),
        penalty=_remaining(user.penalty_hourly_attempts, user.penalty_hour_started_at, limit),
        free_kick=_remaining(user.free_kick_hourly_attempts, user.free_kick_hour_started_at, limit),
        hangman=_remaining(user.hangman_hourly_attempts, user.hangman_hour_started_at, limit),
        tactico=_remaining(user.tactico_hourly_attempts, user.tactico_hour_started_at, limit),
        pairs=_remaining(user.pairs_hourly_attempts, user.pairs_hour_started_at, limit),
    )
