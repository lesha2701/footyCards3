"""Anti-bot: a script playing around the clock topped the ratings and farmed
coins. A human sleeps; a script doesn't. Two rules (GameConfig):

- «усталость»: every game action (a POST to a game API) extends the current
  stretch of play; a gap of anti_bot_rest_hours ends it. After
  anti_bot_max_streak_hours in one stretch, games stop paying coins and
  moving rating (User.game_rewards_blocked) until the player has rested
  anti_bot_rest_hours. A human who plays all day and sleeps never hits it.
- ranked_daily_limit: matches a day, per rating mode (Card Arena, Тактико,
  Мордобой, Стратего, Контратака, Пенальти), that move points / rating; later
  ones still play and pay, they just don't rank — the top is about skill,
  not hours online.

Tracking is written at most every TRACK_EVERY so a burst of requests costs
one UPDATE.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.timeutil import ensure_aware, local_today
from app.models.game_config import GameConfig
from app.models.user import User

TRACK_EVERY = timedelta(minutes=5)
# API prefixes (after /api/v1) whose POSTs are game actions.
GAME_PREFIXES = (
    "/games", "/matches", "/tactico", "/stratego", "/magnate", "/blackjack", "/mordoboi", "/kontra",
    "/path", "/career", "/player-career", "/manager", "/my-player",
)


def is_game_action(method: str, path: str) -> bool:
    if method not in ("POST", "PUT", "PATCH"):
        return False
    rest = path.split("/api/v1", 1)[-1]
    return any(rest == p or rest.startswith(p + "/") for p in GAME_PREFIXES)


def next_state(user: User, config: GameConfig, now: datetime) -> Optional[dict]:
    """New (play_streak_started_at, last_play_at, rest_required_until) after a
    game action at `now`, or None when nothing needs writing yet."""
    rest = timedelta(hours=max(1, config.anti_bot_rest_hours))
    max_streak = timedelta(hours=max(1, config.anti_bot_max_streak_hours))
    last = ensure_aware(user.last_play_at) if user.last_play_at else None
    started = ensure_aware(user.play_streak_started_at) if user.play_streak_started_at else None
    resting = user.rest_required_until is not None and ensure_aware(user.rest_required_until) > now
    from app.services import presence_service

    if last is not None and now - last < TRACK_EVERY and not resting and not presence_service.due(user, config, now):
        return None
    new_stretch = started is None or last is None or now - last >= rest
    if new_stretch:
        started = now  # rested long enough: a new stretch
    until = user.rest_required_until
    if config.anti_bot_enabled and now - started >= max_streak:
        until = now + rest  # still at it: the rest starts from the last action
    values = {"play_streak_started_at": started, "last_play_at": now, "rest_required_until": until}
    values.update(presence_service.next_values(user, config, now, new_stretch))
    return values


async def track_play(db: AsyncSession, user: User) -> None:
    """Called for every game action (core/dependencies.get_current_user)."""
    config = await db.get(GameConfig, 1)  # identity map; never creates the row
    if config is None or not (config.anti_bot_enabled or config.presence_check_enabled):
        return
    values = next_state(user, config, datetime.now(timezone.utc))
    if values is None:
        return
    await db.execute(update(User).where(User.id == user.id).values(**values))
    await db.commit()
    for key, value in values.items():
        set_committed_value(user, key, value)


RANKED_MODES = ("arena", "tactico", "mordoboi", "stratego", "kontra", "penalty")


def take_ranked_slot(user: User, config: GameConfig, mode: str) -> bool:
    """Whether a match this (row-locked) player finishes now may move their
    rating in `mode`; uses up one of today's ranked_daily_limit slots if so.
    Never while resting / blocked. The caller commits."""
    if user.game_rewards_blocked:
        return False
    today = local_today().isoformat()
    data = dict(user.ranked_today or {})
    if data.get("day") != today:
        data = {"day": today}
    used = int(data.get(mode, 0))
    if config.ranked_daily_limit > 0 and used >= config.ranked_daily_limit:
        return False
    data[mode] = used + 1
    user.ranked_today = data
    return True


def status(user: User, config: GameConfig) -> dict:
    """For the player: are games paying, and if not, until when to rest."""
    now = datetime.now(timezone.utc)
    until = ensure_aware(user.rest_required_until) if user.rest_required_until else None
    resting = bool(config.anti_bot_enabled and until and until > now)
    return {"resting": resting, "rest_until": until if resting else None, "rest_hours": config.anti_bot_rest_hours}
