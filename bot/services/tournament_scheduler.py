import asyncio
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from config import get_bot_settings

logger = logging.getLogger(__name__)
settings = get_bot_settings()

SIMULATION_SLOTS: list[tuple[int, int]] = [(12, 0), (20, 0)]
REMINDER_LEAD_MINUTES = 60
LOOP_CHECK_INTERVAL_SECONDS = 900  # 15 min — frequent enough to catch a slot within a reasonable window, cheap enough to run forever

_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _due_slots(
    now: datetime, last_fired: dict[tuple[int, int], date], lead_minutes: int = 0
) -> list[tuple[int, int]]:
    """Pure decision function — deliberately has no I/O so it's fast and
    deterministic to test in isolation. A slot is due once `now` has passed
    its fire time (the slot itself, or `lead_minutes` earlier for the
    reminder loop) and it hasn't already fired today. Catch-up is implicit:
    a slot whose fire time passed hours ago and never fired today is still
    "due" — this is what keeps a bot restart or transient outage from
    silently skipping a whole day's slot."""
    due = []
    for slot in SIMULATION_SLOTS:
        fire_at = now.replace(hour=slot[0], minute=slot[1], second=0, microsecond=0)
        if lead_minutes:
            fire_at -= timedelta(minutes=lead_minutes)
        if now >= fire_at and last_fired.get(slot) != now.date():
            due.append(slot)
    return due


async def _post_internal(path: str) -> dict:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(f"{settings.internal_backend_url}/internal{path}", headers=_HEADERS) as resp:
            resp.raise_for_status()
            return await resp.json()


async def run_simulation_loop() -> None:
    """Fires POST /internal/clubs/simulate-round at each of SIMULATION_SLOTS,
    once per slot per day, with catch-up (see _due_slots). simulate_next_round
    is idempotent (per-Tournament row lock), so a duplicate/late fire is safe
    — the risk this loop protects against is a MISSED fire, not a double one."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired):
                data = await _post_internal("/clubs/simulate-round")
                logger.info("Tournament round simulation fired for slot %s: %s matches", slot, data.get("matches_simulated"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Tournament simulation loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_lineup_reminder_loop() -> None:
    """Fires POST /internal/clubs/lineup-reminders REMINDER_LEAD_MINUTES
    before each simulation slot, once per slot per day, with the same
    catch-up behavior as run_simulation_loop."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=REMINDER_LEAD_MINUTES):
                data = await _post_internal("/clubs/lineup-reminders")
                logger.info("Lineup reminders fired for slot %s: %s clubs notified", slot, data.get("clubs_notified"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Lineup reminder loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)
