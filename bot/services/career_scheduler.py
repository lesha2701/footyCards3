import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import get_bot_settings
from services.tournament_scheduler import LOOP_CHECK_INTERVAL_SECONDS, _due_slots, _post_internal

logger = logging.getLogger(__name__)
settings = get_bot_settings()

# Keep in sync with backend/app/services/career_service.CAREER_SLOTS.
CAREER_SLOTS: list[tuple[int, int]] = [(12, 0), (19, 0)]
# "Скоро тур — проверь состав" goes out this long before each slot.
REMINDER_LEAD_MINUTES = 30


async def _run(path: str, label: str, lead_minutes: int) -> None:
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=lead_minutes, slots=CAREER_SLOTS):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal(path, slot_key)
                logger.info("%s fired for slot %s: %s", label, slot, data)
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("%s loop iteration failed", label)
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_career_reminder_loop() -> None:
    """Pings every human in an active season ~30 min before a round. The
    backend sends at most one reminder per season round, so duplicate or
    late fires are harmless."""
    await _run("/career/reminders", "Career reminders", REMINDER_LEAD_MINUTES)


async def run_career_round_loop() -> None:
    """Plays due "Карьера тренера" rounds at the two daily slots (with
    catch-up after downtime). Each season row is locked backend-side and a
    round is only played once, so duplicate or late fires are harmless; the
    Mini App also catches up lazily when a player opens the career screen."""
    await _run("/career/resolve-due", "Career rounds", 0)


# Live match centre: the second half of a round is played after the
# half-time break (GameConfig.career_halftime_minutes, 10 by default), so
# rounds are also resolved every minute for this long after each slot.
LIVE_WINDOW_MINUTES = 40
LIVE_POLL_SECONDS = 60


async def run_career_live_loop() -> None:
    """Plays the second halves when the break ends, even if every player
    has closed the app (resolve-due is idempotent; outside the windows
    after the slots it does nothing)."""
    tz = ZoneInfo(settings.timezone)
    while True:
        try:
            now = datetime.now(tz)
            for hour, minute in CAREER_SLOTS:
                start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if 0 < (now - start).total_seconds() <= LIVE_WINDOW_MINUTES * 60:
                    slot_key = f"{now.date().isoformat()}T{hour:02d}:{minute:02d}-live"
                    await _post_internal("/career/resolve-due", slot_key)
                    break
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Career live loop iteration failed")
        await asyncio.sleep(LIVE_POLL_SECONDS)


async def run_career_digest_loop() -> None:
    """Weekly career digest («итоги недели»): fired at the career slots; the
    backend sends once per ISO week per coach."""
    await _run("/career/digest", "Career digest", 0)


async def run_club_league_loop() -> None:
    """Pays out last week's «Лига клубов» at the career slots. The backend
    settles a week at most once (and the Mini App settles lazily too), so
    every fire after the first one on a Monday is a no-op."""
    await _run("/clubs/league/settle", "Club league", 0)
