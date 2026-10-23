import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# The automatic «Матч дня» spends at most three API-Football requests a pass
# (the free plan allows 100 a day) and only when there is something to do —
# a match to score or no open match — so half an hour is safe.
MATCH_DAY_SYNC_INTERVAL_SECONDS = 1800


async def run_match_day_sync_loop() -> None:
    """Asks the backend to pick the next «Матч дня» from API-Football and to
    fetch the score of the finished one. The backend does nothing while the
    automatic mode is off in the admin."""
    while True:
        try:
            data = await _post_internal("/match-day/sync", "tick")
            if data.get("status") and data["status"] != "выключено":
                logger.info("Match day sync: %s", data["status"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Match day sync loop iteration failed")
        await asyncio.sleep(MATCH_DAY_SYNC_INTERVAL_SECONDS)
