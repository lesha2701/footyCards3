import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# The digest goes out once a local day after GameConfig.prospect.notify_hour;
# duels expire after hours. Ten minutes is precise enough and cheap.
PROSPECT_SWEEP_INTERVAL_SECONDS = 600


async def run_prospect_sweep_loop() -> None:
    """«Воспитанник Академии»: expires friends' duels, pays last week's
    cohort prizes and queues the evening digest (backend /prospect/sweep,
    once-only via prospect_ledger). The notifications go out through the
    usual dispatcher."""
    while True:
        try:
            data = await _post_internal("/prospect/sweep", "tick")
            if data.get("reminders") or data.get("prizes") or data.get("duels"):
                logger.info("Prospect sweep: %s", data)
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Prospect sweep loop iteration failed")
        await asyncio.sleep(PROSPECT_SWEEP_INTERVAL_SECONDS)
