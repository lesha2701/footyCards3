import logging

import aiohttp
from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from config import get_bot_settings

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
    payment = message.successful_payment
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(
                f"{settings.internal_backend_url}/internal/stars-payments/deliver",
                json={
                    "payload_token": payment.invoice_payload,
                    "telegram_user_id": message.from_user.id,
                    "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                    "total_amount": payment.total_amount,
                },
                headers=_HEADERS,
            ) as resp:
                ok = resp.status == 200
                if not ok:
                    logger.error("stars payment delivery failed: status=%s body=%s", resp.status, await resp.text())
    except Exception:
        logger.exception("stars payment delivery call failed")
        ok = False

    if ok:
        await message.answer("🎉 Пак куплен и уже в твоей коллекции! Открой приложение, чтобы посмотреть карточку.")
    else:
        # The payment went through on Telegram's side regardless of whether
        # our delivery call succeeded — never leave the player without their
        # pack. Loud enough to notice and retry by hand if this ever fires.
        await message.answer(
            "⭐ Оплата прошла, но при начислении пака произошла ошибка. Мы разберёмся и начислим его вручную — "
            "напиши в поддержку, если пак не появится в течение нескольких минут."
        )
        logger.critical(
            "UNDELIVERED stars payment: charge_id=%s user=%s payload=%s",
            payment.telegram_payment_charge_id, message.from_user.id, payment.invoice_payload,
        )
