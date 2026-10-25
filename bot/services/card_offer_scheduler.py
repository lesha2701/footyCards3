import asyncio
import logging

from services.tournament_scheduler import _post_internal

logger = logging.getLogger(__name__)

# «Осталось 3 часа» goes out once per offer (card_offers.reminded_at); a
# five-minute tick is precise enough and a no-op the rest of the time.
CARD_OFFER_REMIND_INTERVAL_SECONDS = 300


async def run_card_offer_reminder_loop() -> None:
    """Reminds players who looked at a «Карты ⭐» offer and didn't buy it
    that it ends within three hours (the backend picks who and when)."""
    while True:
        try:
            data = await _post_internal("/card-offers/remind", "tick")
            if data.get("sent"):
                logger.info("Card offer reminders queued: %s", data["sent"])
        except Exception:  # noqa: BLE001 - keep the loop alive across transient HTTP/network errors
            logger.exception("Card offer reminder loop iteration failed")
        await asyncio.sleep(CARD_OFFER_REMIND_INTERVAL_SECONDS)
