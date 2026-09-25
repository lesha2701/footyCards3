import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from config import get_bot_settings
from services.tournament_scheduler import LOOP_CHECK_INTERVAL_SECONDS, REMINDER_LEAD_MINUTES, _due_slots, _post_internal

logger = logging.getLogger(__name__)
settings = get_bot_settings()

# Keep in sync with backend/app/services/player_tournament_fixture_service.SIMULATION_SLOTS.
# 21:00, not 20:00 — 20:00 is the club tournament slot.
PLAYER_TOURNAMENT_SLOTS: list[tuple[int, int]] = [(10, 0), (15, 0), (21, 0)]


async def _run_loop(path: str, label: str, lead_minutes: int) -> None:
    """Same design as tournament_scheduler.run_simulation_loop: fire each due
    slot once per day with catch-up; duplicate/late fires are made no-ops by
    the backend's slot_key dedup (TournamentSimulationSlotLog)."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=lead_minutes, slots=PLAYER_TOURNAMENT_SLOTS):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal(path, slot_key)
                logger.info("%s fired for slot %s (key %s): %s", label, slot, slot_key, data)
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("%s loop iteration failed", label)
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)


async def run_player_tournament_simulation_loop() -> None:
    await _run_loop("/player-tournaments/simulate-round", "Player tournament simulation", 0)


async def run_player_tournament_reminder_loop() -> None:
    await _run_loop("/player-tournaments/lineup-reminders", "Player tournament reminders", REMINDER_LEAD_MINUTES)
