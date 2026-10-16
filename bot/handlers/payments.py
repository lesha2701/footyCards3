import logging

import aiohttp
from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

import db
from config import get_bot_settings
from services import stars_delivery

router = Router(name="payments")
settings = get_bot_settings()
logger = logging.getLogger("footycards.bot.payments")

_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
_TIMEOUT = aiohttp.ClientTimeout(total=8)  # stays well under Telegram's 10s pre_checkout_query deadline


@router.pre_checkout_query()
async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{settings.internal_backend_url}/internal/stars-payments/pre-checkout",
                json={
                    "payload_token": pre_checkout_query.invoice_payload,
                    "total_amount": pre_checkout_query.total_amount,
                },
                headers=_HEADERS,
            ) as resp:
                data = await resp.json()
    except Exception:
        logger.exception("pre_checkout_query validation call failed")
        await pre_checkout_query.answer(ok=False, error_message="Что-то пошло не так, попробуй ещё раз позже.")
        return

    if resp.status != 200 or not data.get("ok"):
        error_message = data.get("error_message") or "Этот заказ больше не действителен."
        await pre_checkout_query.answer(ok=False, error_message=error_message)
        return

    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def handle_successful_payment(message: Message) -> None:
    """Telegram has already charged the player at this point. The payment
    is written to stars_payment_receipts first (straight into Postgres, so
    it survives even a backend outage), then delivered; a failed delivery
    is retried by services/stars_delivery.run_stars_payment_retry_loop and
    shows up in the admin panel — never just a log line."""
    payment = message.successful_payment
    telegram_user_id = message.from_user.id
    try:
        await db.record_stars_payment(
            payment.telegram_payment_charge_id, payment.invoice_payload, telegram_user_id, payment.total_amount,
            stars_delivery.FIRST_RETRY_DELAY_SECONDS,
        )
    except Exception:
        # Delivery below still records it backend-side; this only matters
        # if the backend is down as well.
        logger.exception("could not record stars payment receipt")

    outcome = await stars_delivery.deliver(
        payment.invoice_payload, telegram_user_id, payment.telegram_payment_charge_id, payment.total_amount,
    )
    if outcome.ok:
        await message.answer(stars_delivery.success_text(outcome.body))
        return

    logger.critical(
        "UNDELIVERED stars payment (will retry): charge_id=%s user=%s payload=%s",
        payment.telegram_payment_charge_id, telegram_user_id, payment.invoice_payload,
    )
    await message.answer(stars_delivery.DELAYED_TEXT)
    await stars_delivery.alert_admins(message.bot, stars_delivery.admin_alert_text(
        telegram_user_id, payment.total_amount, payment.telegram_payment_charge_id, outcome.error, 1,
    ))
