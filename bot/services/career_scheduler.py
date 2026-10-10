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


async def run_career_round_loop() -> None:
    """Plays due "Карьера тренера" rounds at the two daily slots (with
    catch-up after downtime). Each season row is locked backend-side and a
    round is only played once, so duplicate or late fires are harmless; the
    Mini App also catches up lazily when a player opens the career screen."""
    tz = ZoneInfo(settings.timezone)
    last_fired: dict[tuple[int, int], date] = {}
    while True:
        try:
            now = datetime.now(tz)
            for slot in _due_slots(now, last_fired, lead_minutes=0, slots=CAREER_SLOTS):
                slot_key = f"{now.date().isoformat()}T{slot[0]:02d}:{slot[1]:02d}"
                data = await _post_internal("/career/resolve-due", slot_key)
                logger.info("Career rounds fired for slot %s: %s", slot, data)
                last_fired[slot] = now.date()
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Career round loop iteration failed")
        await asyncio.sleep(LOOP_CHECK_INTERVAL_SECONDS)
