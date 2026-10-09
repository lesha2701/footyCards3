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


_COLUMNS = {
    "memory": "memory", "arena": "match", "saboteur": "saboteur", "penalty": "penalty",
    "free_kick": "free_kick", "hangman": "hangman", "tactico": "tactico", "pairs": "pairs",
}


def _resets_at(user: User, limit: int) -> dict[str, datetime]:
    resets: dict[str, datetime] = {}
    for field, column in _COLUMNS.items():
        started = getattr(user, f"{column}_hour_started_at")
        if started is not None and _remaining(getattr(user, f"{column}_hourly_attempts"), started, limit) == 0:
            resets[field] = ensure_aware(started) + timedelta(hours=1)
    return resets


def get_remaining_plays(user: User, config: GameConfig) -> GameLimitsOut:
    limit = config.hourly_game_limit
    return GameLimitsOut(
        hourly_limit=limit,
        resets_at=_resets_at(user, limit),
        memory=_remaining(user.memory_hourly_attempts, user.memory_hour_started_at, limit),
        arena=_remaining(user.match_hourly_attempts, user.match_hour_started_at, limit),
        saboteur=_remaining(user.saboteur_hourly_attempts, user.saboteur_hour_started_at, limit),
        penalty=_remaining(user.penalty_hourly_attempts, user.penalty_hour_started_at, limit),
        free_kick=_remaining(user.free_kick_hourly_attempts, user.free_kick_hour_started_at, limit),
        hangman=_remaining(user.hangman_hourly_attempts, user.hangman_hour_started_at, limit),
        tactico=_remaining(user.tactico_hourly_attempts, user.tactico_hour_started_at, limit),
        pairs=_remaining(user.pairs_hourly_attempts, user.pairs_hour_started_at, limit),
    )
