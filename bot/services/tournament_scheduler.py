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


async def _post_internal(path: str, slot_key: str) -> dict:
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(
            f"{settings.internal_backend_url}/internal{path}", headers=_HEADERS, params={"slot_key": slot_key}
        ) as resp:
            resp.raise_for_status()
            return await resp.json()


async def run_simulation_loop() -> None:
    """Fires POST /internal/clubs/simulate-round at each of SIMULATION_SLOTS,
    once per slot per day, with catch-up (see _due_slots). The per-Tournament
    row lock in simulate_next_round only makes two *concurrent* calls safe —
    it does NOT protect against a duplicate/late fire hours or days apart (a
    bot restart resets this loop's in-memory last_fired dict and would
    otherwise re-fire an already-processed slot). That is instead guarded by
    slot_key: it's derived from the due slot's nominal time (not wall-clock
    now), passed to the backend, and try-inserted against
    TournamentSimulationSlotLog there — a duplicate key makes the call a
    genuine no-op regardless of in-memory state."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal("/clubs/simulate-round", slot_key)
                logger.info("Tournament round simulation fired for slot %s (key %s): %s matches", slot, slot_key, data.get("matches_simulated"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Tournament simulation loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_lineup_reminder_loop() -> None:
    """Fires POST /internal/clubs/lineup-reminders REMINDER_LEAD_MINUTES
    before each simulation slot, once per slot per day, with the same
    catch-up behavior and slot_key-based backend dedup as run_simulation_loop
    (see its docstring) — the slot_key is built from the slot itself, not
    the lead-adjusted fire time, so it lines up date/time-wise with the
    corresponding simulate_round call even though the two are deduped
    independently (different `kind`, same `slot_key`)."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=REMINDER_LEAD_MINUTES):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal("/clubs/lineup-reminders", slot_key)
                logger.info("Lineup reminders fired for slot %s (key %s): %s clubs notified", slot, slot_key, data.get("clubs_notified"))
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Lineup reminder loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)
