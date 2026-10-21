import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# «Менеджер» rounds run at their own slots (GameConfig.manager_slots), three a
# day; checking every two minutes keeps them on time and is cheap when nothing
# is due.
MANAGER_SWEEP_INTERVAL_SECONDS = 120


async def run_manager_sweep_loop() -> None:
    """Starts the «Менеджер» season when the preseason closes and plays the
    due rounds of every manager league. The backend guards the season start
    with its primary key and locks each league row, so the Mini App's own
    lazy sweep and a second bot replica never play a round twice."""
    while True:
        try:
            data = await _post_internal("/manager/sweep", "tick")
            if data.get("matches_simulated"):
                logger.info("Manager sweep played %s round(s)", data["matches_simulated"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Manager sweep loop iteration failed")
        await asyncio.sleep(MANAGER_SWEEP_INTERVAL_SECONDS)
