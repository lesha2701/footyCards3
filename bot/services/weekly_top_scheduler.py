import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# «Топ недели» pays once a week, right after Monday 00:00 (local time);
# checking every five minutes is enough and a no-op the rest of the week.
WEEKLY_TOP_INTERVAL_SECONDS = 300


async def run_weekly_top_loop() -> None:
    """Settles the closed week's «Топ недели». The backend's WeeklyTopRun
    primary key makes it pay once, whoever (bot or Mini App) gets there first."""
    while True:
        try:
            data = await _post_internal("/weekly-top/settle", "tick")
            if data.get("paid"):
                logger.info("Weekly top settled: %s places paid", data["paid"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Weekly top loop iteration failed")
        await asyncio.sleep(WEEKLY_TOP_INTERVAL_SECONDS)
