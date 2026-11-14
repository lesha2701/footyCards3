from datetime import datetime, timedelta, timezone

from app.core.timeutil import ensure_aware, local_today
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
    "stratego": "stratego", "magnate": "magnate", "mordoboi": "mordoboi", "kontra": "kontra",
    "magic": "magic",
    "one_on_one": "one_on_one", "otvetka": "otvetka", "fergie_time": "fergie",
}


def _resets_at(user: User, limit: int, free_kick_limit: int) -> dict[str, datetime]:
    resets: dict[str, datetime] = {}
    for field, column in _COLUMNS.items():
        started = getattr(user, f"{column}_hour_started_at")
        cap = free_kick_limit if field == "free_kick" else limit
        if field == "free_kick" and user.free_kick_bonus_series > 0:
            continue  # a bought series is waiting: playable now
        if started is not None and _remaining(getattr(user, f"{column}_hourly_attempts"), started, cap) == 0:
            resets[field] = ensure_aware(started) + timedelta(hours=1)
    return resets


def _ranked_done(user: User, config: GameConfig) -> list[str]:
    from app.services.anti_bot_service import RANKED_MODES

    data = user.ranked_today or {}
    if config.ranked_daily_limit <= 0 or data.get("day") != local_today().isoformat():
        return []
    return [mode for mode in RANKED_MODES if int(data.get(mode, 0)) >= config.ranked_daily_limit]


def get_remaining_plays(user: User, config: GameConfig) -> GameLimitsOut:
    limit = config.hourly_game_limit
    free_kick_limit = config.free_kick_hourly_limit
    rest_until = None
    if config.anti_bot_enabled and user.anti_bot_watch and user.rest_required_until is not None:
        until = ensure_aware(user.rest_required_until)
        if until > datetime.now(timezone.utc):
            rest_until = until
    return GameLimitsOut(
        rest_until=rest_until,
        rest_hours=config.anti_bot_rest_hours,
        ranked_limit=config.ranked_daily_limit,
        ranked_done=_ranked_done(user, config),
        hourly_limit=limit,
        free_kick_hourly_limit=free_kick_limit,
        resets_at=_resets_at(user, limit, free_kick_limit),
        memory=_remaining(user.memory_hourly_attempts, user.memory_hour_started_at, limit),
        arena=_remaining(user.match_hourly_attempts, user.match_hour_started_at, limit),
        saboteur=_remaining(user.saboteur_hourly_attempts, user.saboteur_hour_started_at, limit),
        penalty=_remaining(user.penalty_hourly_attempts, user.penalty_hour_started_at, limit),
        free_kick=_remaining(user.free_kick_hourly_attempts, user.free_kick_hour_started_at, free_kick_limit)
        + user.free_kick_bonus_series,
        hangman=_remaining(user.hangman_hourly_attempts, user.hangman_hour_started_at, limit),
        tactico=_remaining(user.tactico_hourly_attempts, user.tactico_hour_started_at, limit),
        pairs=_remaining(user.pairs_hourly_attempts, user.pairs_hour_started_at, limit),
        stratego=_remaining(user.stratego_hourly_attempts, user.stratego_hour_started_at, limit),
        magnate=_remaining(user.magnate_hourly_attempts, user.magnate_hour_started_at, limit),
        mordoboi=_remaining(user.mordoboi_hourly_attempts, user.mordoboi_hour_started_at, limit),
        kontra=_remaining(user.kontra_hourly_attempts, user.kontra_hour_started_at, limit),
        magic=_remaining(user.magic_hourly_attempts, user.magic_hour_started_at, limit),
        one_on_one=_remaining(user.one_on_one_hourly_attempts, user.one_on_one_hour_started_at, limit),
        otvetka=_remaining(user.otvetka_hourly_attempts, user.otvetka_hour_started_at, limit),
        fergie_time=_remaining(user.fergie_hourly_attempts, user.fergie_hour_started_at, limit),
    )
