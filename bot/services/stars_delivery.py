"""Delivering paid Telegram Stars orders: the call to the backend shared by
the successful_payment handler and the retry loop, plus the texts the
player and the admins get."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import db
from config import get_bot_settings
from keyboards import open_app_keyboard

settings = get_bot_settings()
logger = logging.getLogger("footycards.bot.stars")

_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
# Delivery opens packs, grants collection rewards etc. — give it far more
# room than pre_checkout (which must answer Telegram within 10 s).
DELIVERY_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Must match backend stars_receipt_service.MAX_AUTO_ATTEMPTS: after this many
# failed attempts a receipt waits for an admin (retry / refund in the panel).
MAX_AUTO_ATTEMPTS = 8
# The handler delivers right away; the retry loop only picks a receipt up
# after this, so the two don't race on a fresh payment.
FIRST_RETRY_DELAY_SECONDS = 180
# Backend unreachable: try again this much later (attempt not counted).
UNREACHABLE_RETRY_SECONDS = 120
RETRY_LOOP_INTERVAL_SECONDS = 60


@dataclass
class DeliveryOutcome:
    ok: bool
    body: dict = field(default_factory=dict)
    # None = the backend wasn't reached (network error/timeout), so it
    # couldn't record the attempt itself.
    status: Optional[int] = None
    error: str = ""


async def deliver(
    payload_token: str, telegram_user_id: int, charge_id: str, total_amount: int,
    subscription: Optional[dict] = None,
) -> DeliveryOutcome:
    """`subscription`: the Telegram Stars subscription fields of the payment
    (subscription_expiration_date / is_recurring / is_first_recurring), when
    known — only the live successful_payment has them, retries don't."""
    try:
        async with aiohttp.ClientSession(timeout=DELIVERY_TIMEOUT) as session:
            async with session.post(
                f"{settings.internal_backend_url}/internal/stars-payments/deliver",
                json={
                    "payload_token": payload_token,
                    "telegram_user_id": telegram_user_id,
                    "telegram_payment_charge_id": charge_id,
                    "total_amount": total_amount,
                    **(subscription or {}),
                },
                headers=_HEADERS,
            ) as resp:
                if resp.status == 200:
                    return DeliveryOutcome(ok=True, body=await resp.json(), status=200)
                text = await resp.text()
                logger.error("stars payment delivery failed: status=%s body=%s", resp.status, text)
                return DeliveryOutcome(ok=False, status=resp.status, error=text[:300])
    except Exception as exc:  # noqa: BLE001 - any failure here just means "retry later"
        logger.exception("stars payment delivery call failed")
        return DeliveryOutcome(ok=False, status=None, error=f"{type(exc).__name__}: {exc}"[:300])


SHOP_TEXTS = {
    "calendar_catchup": "📅 Пропущенный день календаря наград получен! Открой приложение.",
    "cosmetic": "✨ Украшение куплено! Надень его в профиле → «Стиль».",
    "club_pass": "🎟 Клубный абонемент активен! Забирай ежедневный бонус в приложении.",
    "club_pass_renewal": "🎟 Клубный абонемент продлён ещё на 30 дней. Спасибо, что ты с нами!",
    "season_premium": "🏆 Сезонный пропуск открыт! Забери премиум-награды в приложении.",
    "starter_offer": "🎁 Стартовый набор зачислен! Открой приложение и забирай.",
}


def success_text(body: dict) -> str:
    """Which result field is set tells what was bought (StarsInvoiceStatusOut)."""
    shop = body.get("shop_result")
    if shop is not None:
        kind = "club_pass_renewal" if shop.get("renewal") else shop.get("kind", "")
        return SHOP_TEXTS.get(kind, "⭐ Покупка зачислена! Открой приложение.")
    if body.get("gift_result") is not None:
        return "🎁 Подарок отправлен! Получатель сможет открыть его в приложении."
    if body.get("blackjack_result") is not None:
        return "🃏 Попытка в «21» куплена! Открой приложение, чтобы сыграть с Тренером соперника."
    if body.get("wheel_result") is not None:
        return "🎡 Колесо фортуны крутится — открой приложение, чтобы увидеть свой приз!"
    if body.get("coin_result") is not None:
        return "⭐ Монеты зачислены! Открой приложение, чтобы увидеть баланс."
    if body.get("my_player_result") is not None:
        return "⭐ Покупка для «Моего игрока» зачислена! Открой приложение."
    if body.get("path_result") is not None:
        return "⭐ Покупка для Академии зачислена! Открой приложение."
    return "🎉 Пак куплен и уже в твоей коллекции! Открой приложение, чтобы посмотреть карточку."


DELAYED_TEXT = (
    "⭐ Оплата прошла, но начисление покупки задержалось. Не переживай — мы автоматически "
    "повторим его в ближайшие минуты и пришлём сообщение, как только всё будет готово.\n\n"
    "Если что-то не так — напиши /paysupport."
)

GAVE_UP_TEXT = (
    "⭐ Не получилось автоматически начислить твою покупку. Мы уже разбираемся: начислим её вручную "
    "или вернём звёзды. Если есть вопросы — напиши /paysupport."
)


async def safe_send(bot: Bot, chat_id: int, text: str, with_app_button: bool = False) -> None:
    try:
        await bot.send_message(chat_id, text, reply_markup=open_app_keyboard() if with_app_button else None)
    except TelegramAPIError as exc:
        logger.warning("could not message %s: %s", chat_id, exc)


async def alert_admins(bot: Bot, text: str) -> None:
    for admin_id in settings.admin_ids:
        await safe_send(bot, admin_id, text)


def admin_alert_text(telegram_user_id: int, amount: int, charge_id: str, error: str, attempt: int) -> str:
    return (
        f"⚠️ <b>Не удалось начислить оплату Stars</b> (попытка {attempt})\n"
        f"Игрок: <code>{telegram_user_id}</code>, сумма: {amount} ⭐\n"
        f"Платёж: <code>{charge_id[:40]}…</code>\n"
        f"Ошибка: {error[:200] or '—'}\n\n"
        "Бот повторит сам. Вручную: админка → Магазин → Платежи Stars."
    )


async def retry_due_receipts(bot: Bot) -> int:
    """One pass of the retry loop. Returns how many receipts got delivered."""
    delivered = 0
    for row in await db.fetch_due_stars_receipts(MAX_AUTO_ATTEMPTS):
        outcome = await deliver(row["payload_token"], row["telegram_user_id"], row["telegram_payment_charge_id"],
                                row["total_amount"])
        if outcome.ok:
            delivered += 1
            await safe_send(bot, row["telegram_user_id"], "✅ Покупка начислена, извини за задержку!\n\n"
                            + success_text(outcome.body), with_app_button=True)
            continue
        if outcome.status is None:
            await db.postpone_stars_receipt(row["id"], UNREACHABLE_RETRY_SECONDS)
            continue
        # The backend recorded the failed attempt (attempts + 1) itself.
        if row["attempts"] + 1 >= MAX_AUTO_ATTEMPTS:
            await safe_send(bot, row["telegram_user_id"], GAVE_UP_TEXT)
            await alert_admins(bot, admin_alert_text(
                row["telegram_user_id"], row["total_amount"], row["telegram_payment_charge_id"], outcome.error,
                row["attempts"] + 1,
            ) + "\n\n<b>Автоповторы закончились — нужно решение админа.</b>")
    return delivered


async def run_stars_payment_retry_loop(bot: Bot) -> None:
    while True:
        try:
            delivered = await retry_due_receipts(bot)
            if delivered:
                logger.info("stars retry loop: delivered %s receipt(s)", delivered)
        except Exception:  # noqa: BLE001 - keep the loop alive
            logger.exception("stars retry loop iteration failed")
        await asyncio.sleep(RETRY_LOOP_INTERVAL_SECONDS)
