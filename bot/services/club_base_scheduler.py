import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# Builds last hours; a minute's delay before the "стройка завершена" push is fine.
CLUB_BASE_SWEEP_INTERVAL_SECONDS = 60


async def run_club_base_sweep_loop() -> None:
    """Completes «Клубная база» constructions whose timer ran out while the
    player was away and queues the notification. The backend takes each
    base with SKIP LOCKED and re-checks it under the lock, so this loop, a
    second bot replica and the player's own request never complete one
    construction twice."""
    while True:
        try:
            data = await _post_internal("/club-base/sweep", "tick")
            if data.get("completed"):
                logger.info("Club base sweep completed %s construction(s)", data["completed"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Club base sweep loop iteration failed")
        await asyncio.sleep(CLUB_BASE_SWEEP_INTERVAL_SECONDS)
