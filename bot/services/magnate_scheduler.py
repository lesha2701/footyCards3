import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# «Футбольный магнат» turns are ~30 s, so the background tick has to be
# frequent; the call is cheap when nothing is due (one indexed query).
MAGNATE_SWEEP_INTERVAL_SECONDS = 10


async def run_magnate_sweep_loop() -> None:
    """Advances «Футбольный магнат» tables nobody is looking at: starts
    public lobbies whose wait ran out (bots take the empty seats), cancels
    or starts expired private rooms, auto-plays expired turns and replaces
    absent players with bots. The backend takes each match with SKIP LOCKED
    and re-checks its deadline under the lock, so this loop, a second bot
    replica and the Mini App's own lazy sweep never process a deadline
    twice."""
    while True:
        try:
            data = await _post_internal("/magnate/sweep", "tick")
            if data.get("advanced"):
                logger.info("Magnate sweep advanced %s match(es)", data["advanced"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Magnate sweep loop iteration failed")
        await asyncio.sleep(MAGNATE_SWEEP_INTERVAL_SECONDS)
