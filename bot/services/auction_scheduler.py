import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# Lots end at a fixed minute, and the winner/seller are waiting on that, so
# the tick is frequent; the call is cheap when nothing is due (one indexed query).
AUCTION_SWEEP_INTERVAL_SECONDS = 15


async def run_auction_sweep_loop() -> None:
    """Settles «Трансферный рынок» lots whose time ran out even when nobody
    has the market open: sells to the leading bid or returns the card to the
    seller. The backend takes each lot with SKIP LOCKED and re-checks it under
    the lock, so this loop, a second bot replica and the Mini App's own lazy
    sweep never settle a lot twice."""
    while True:
        try:
            data = await _post_internal("/auction/sweep", "tick")
            if data.get("closed"):
                logger.info("Auction sweep closed %s lot(s)", data["closed"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Auction sweep loop iteration failed")
        await asyncio.sleep(AUCTION_SWEEP_INTERVAL_SECONDS)
