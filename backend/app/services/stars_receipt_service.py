"""Durable bookkeeping around Stars payment delivery.

Telegram charges the player before we deliver anything, so every
successful_payment gets a StarsPaymentReceipt (the bot inserts it before it
calls us; `_ensure_receipt` covers the case where that insert failed). The
receipt's status follows each delivery attempt: a failure is recorded with
its error and a backoff time, the bot's retry loop re-delivers it, and the
admin panel can re-deliver or refund it by hand. A refunded receipt is
never delivered afterwards, and a delivered one is never refunded — both
decisions are taken under the receipt's row lock."""
import logging
from datetime import timedelta
from typing import Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.core.pagination import Page, PageParams
from app.models.enums import NotificationType
from app.models.gift import GiftSet
from app.models.mixins import utcnow
from app.models.pack import Pack, StarsInvoice
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.models.user import User
from app.schemas.admin import StarsPaymentReceiptOut
from app.schemas.stars import StarsInvoiceStatusOut, StarsPaymentDeliverIn
from app.services import stars_payment_service
from app.services.notification_service import notify

settings = get_settings()
logger = logging.getLogger(__name__)

# The bot retries a failed delivery automatically this many times (with the
# backoff below: 2, 4, 8 … minutes, capped at 6 h — roughly a day in total);
# after that the receipt waits for an admin.
MAX_AUTO_ATTEMPTS = 8
PROBLEM_STATUSES = ("pending", "failed")


def retry_delay(attempts: int) -> timedelta:
    return timedelta(minutes=min(2 ** max(attempts, 1), 360))


def _error_text(exc: Exception) -> str:
    text = exc.message if isinstance(exc, AppError) else f"{type(exc).__name__}: {exc}"
    return text[:500]


async def _lock_receipt(db: AsyncSession, charge_id: str) -> Optional[StarsPaymentReceipt]:
    return (
        await db.execute(
            select(StarsPaymentReceipt)
            .where(StarsPaymentReceipt.telegram_payment_charge_id == charge_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _ensure_receipt(db: AsyncSession, payload: StarsPaymentDeliverIn) -> None:
    """Records the payment if the bot's own insert didn't (committed at once,
    so it survives a failed delivery's rollback)."""
    if await _lock_receipt(db, payload.telegram_payment_charge_id) is None:
        try:
            async with db.begin_nested():
                db.add(StarsPaymentReceipt(
                    telegram_payment_charge_id=payload.telegram_payment_charge_id,
                    payload_token=payload.payload_token,
                    telegram_user_id=payload.telegram_user_id,
                    total_amount=payload.total_amount,
                    status="pending",
                    attempts=0,
                ))
                await db.flush()
        except IntegrityError:
            pass  # the bot's insert won the race — same row either way
    await db.commit()


async def _mark_failed(db: AsyncSession, charge_id: str, exc: Exception) -> None:
    receipt = await _lock_receipt(db, charge_id)
    if receipt is None or receipt.status in ("delivered", "refunded"):
        await db.commit()
        return
    receipt.attempts += 1
    receipt.status = "failed"
    receipt.last_error = _error_text(exc)
    receipt.next_attempt_at = utcnow() + retry_delay(receipt.attempts)
    await db.commit()


async def _mark_delivered(db: AsyncSession, charge_id: str) -> None:
    receipt = await _lock_receipt(db, charge_id)
    if receipt is not None and receipt.status != "delivered":
        receipt.attempts += 1
        receipt.status = "delivered"
        receipt.delivered_at = utcnow()
        receipt.last_error = None
        receipt.next_attempt_at = None
    await db.commit()


async def deliver_with_receipt(db: AsyncSession, payload: StarsPaymentDeliverIn) -> StarsInvoiceStatusOut:
    """Delivers a paid order (stars_payment_service.deliver_payment, which is
    idempotent per invoice) and keeps its receipt in step. Errors are
    recorded on the receipt and re-raised unchanged, so the bot still sees
    the same status codes as before."""
    charge_id = payload.telegram_payment_charge_id
    await _ensure_receipt(db, payload)

    receipt = await _lock_receipt(db, charge_id)
    if receipt.status == "refunded":
        await db.rollback()
        raise ConflictError("Звёзды за этот платёж уже возвращены — покупка не начисляется")

    try:
        result = await stars_payment_service.deliver_payment(
            db, payload.payload_token, payload.telegram_user_id, charge_id, payload.total_amount,
            subscription_expiration=payload.subscription_expiration_date,
        )
    except Exception as exc:
        await db.rollback()
        logger.warning("Stars delivery failed for charge %s: %s", charge_id, _error_text(exc))
        await _mark_failed(db, charge_id, exc)
        raise

    await _mark_delivered(db, charge_id)
    return result


def _payload_of(receipt: StarsPaymentReceipt) -> StarsPaymentDeliverIn:
    return StarsPaymentDeliverIn(
        payload_token=receipt.payload_token,
        telegram_user_id=receipt.telegram_user_id,
        telegram_payment_charge_id=receipt.telegram_payment_charge_id,
        total_amount=receipt.total_amount,
    )


async def _user_by_telegram_id(db: AsyncSession, telegram_id: int) -> Optional[User]:
    return (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()


async def _get_receipt_or_404(db: AsyncSession, receipt_id: int) -> StarsPaymentReceipt:
    receipt = await db.get(StarsPaymentReceipt, receipt_id)
    if receipt is None:
        raise NotFoundError("Платёж не найден")
    return receipt


async def admin_retry(db: AsyncSession, receipt_id: int) -> StarsPaymentReceiptOut:
    receipt = await _get_receipt_or_404(db, receipt_id)
    if receipt.status == "delivered":
        raise ConflictError("Покупка уже начислена")
    if receipt.status == "refunded":
        raise ConflictError("Звёзды уже возвращены — начислить покупку нельзя")
    await deliver_with_receipt(db, _payload_of(receipt))

    user = await _user_by_telegram_id(db, receipt.telegram_user_id)
    if user is not None:
        await notify(
            db, user.id, NotificationType.admin_message, "Покупка начислена",
            f"Твоя покупка за {receipt.total_amount} ⭐ начислена. Извини за задержку!",
            related_object_type="stars_payment_receipt", related_object_id=receipt.id,
        )
        await db.commit()
    return await get_receipt_out(db, receipt.id)


async def _request_telegram_refund(telegram_user_id: int, charge_id: str) -> None:
    """Bot API refundStarPayment. Split out so tests can monkeypatch the one
    Telegram call (same as _request_telegram_invoice_link)."""
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/refundStarPayment"
    try:
        async with httpx.AsyncClient(timeout=10, proxy=settings.telegram_proxy_url or None) as client:
            resp = await client.post(url, json={"user_id": telegram_user_id, "telegram_payment_charge_id": charge_id})
        data = resp.json()
    except httpx.HTTPError:
        logger.warning("refundStarPayment: request to Telegram failed", exc_info=True)
        raise ConflictError("Не удалось связаться с Telegram — попробуй ещё раз") from None
    if not data.get("ok"):
        raise ConflictError(f"Telegram отказал в возврате: {data.get('description', 'неизвестная ошибка')}")


async def admin_refund(db: AsyncSession, receipt_id: int) -> StarsPaymentReceiptOut:
    """Returns the Stars of a payment that was never delivered. Holds the
    receipt's row lock across the Telegram call, so a delivery attempt
    racing it waits and then sees `refunded`."""
    await _get_receipt_or_404(db, receipt_id)
    receipt = (
        await db.execute(
            select(StarsPaymentReceipt).where(StarsPaymentReceipt.id == receipt_id)
            .with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if receipt.status == "refunded":
        raise ConflictError("Звёзды уже возвращены")
    invoice = (
        await db.execute(select(StarsInvoice).where(StarsInvoice.payload_token == receipt.payload_token))
    ).scalar_one_or_none()
    if receipt.status == "delivered" or (invoice is not None and invoice.completed_at is not None):
        raise ConflictError("Покупка уже начислена — возврат звёзд не делаем, иначе игрок получит её бесплатно")

    await _request_telegram_refund(receipt.telegram_user_id, receipt.telegram_payment_charge_id)
    receipt.status = "refunded"
    receipt.refunded_at = utcnow()
    receipt.next_attempt_at = None

    user = await _user_by_telegram_id(db, receipt.telegram_user_id)
    if user is not None:
        await notify(
            db, user.id, NotificationType.admin_message, "Звёзды возвращены",
            f"Покупку не удалось начислить, поэтому мы вернули {receipt.total_amount} ⭐ на твой счёт в Telegram.",
            related_object_type="stars_payment_receipt", related_object_id=receipt.id,
        )
    await db.commit()
    return await get_receipt_out(db, receipt.id)


async def _describe(db: AsyncSession, invoice: Optional[StarsInvoice]) -> str:
    """What the payment was for, in admin-readable words."""
    if invoice is None:
        return "Счёт не найден"
    if invoice.pack_id is not None:
        pack = await db.get(Pack, invoice.pack_id)
        return f"Пак «{pack.name}»" if pack else "Пак"
    if invoice.gift_set_id is not None:
        gift_set = await db.get(GiftSet, invoice.gift_set_id)
        return f"Подарок «{gift_set.name}»" if gift_set else "Подарок"
    if invoice.is_wheel_spin:
        return "Вращение колеса"
    if invoice.my_player_purchase:
        return "«Мой игрок»: " + ("тренировка" if invoice.my_player_purchase == "training" else "предмет")
    if invoice.is_blackjack_entry:
        return "Попытка в «21»"
    if invoice.path_user_card_id is not None:
        return "Попытка «Академии»"
    if invoice.academy_speedup:
        return "Ускорение Академии"
    if invoice.shop_product:
        from app.services.shop_product_service import label

        return label(invoice.shop_product)
    if invoice.coins_amount:
        return f"{invoice.coins_amount} монет"
    return "Покупка"


async def _to_out(db: AsyncSession, receipt: StarsPaymentReceipt) -> StarsPaymentReceiptOut:
    invoice = (
        await db.execute(select(StarsInvoice).where(StarsInvoice.payload_token == receipt.payload_token))
    ).scalar_one_or_none()
    user = await _user_by_telegram_id(db, receipt.telegram_user_id)
    return StarsPaymentReceiptOut(
        id=receipt.id,
        telegram_payment_charge_id=receipt.telegram_payment_charge_id,
        telegram_user_id=receipt.telegram_user_id,
        user_id=user.id if user else None,
        user_username=user.username if user else None,
        user_display_name=user.full_display_name() if user else None,
        product=await _describe(db, invoice),
        stars_amount=receipt.total_amount,
        status=receipt.status,
        attempts=receipt.attempts,
        last_error=receipt.last_error,
        next_attempt_at=receipt.next_attempt_at,
        auto_retry=receipt.status in PROBLEM_STATUSES and receipt.attempts < MAX_AUTO_ATTEMPTS,
        created_at=receipt.created_at,
        delivered_at=receipt.delivered_at,
        refunded_at=receipt.refunded_at,
    )


async def get_receipt_out(db: AsyncSession, receipt_id: int) -> StarsPaymentReceiptOut:
    return await _to_out(db, await _get_receipt_or_404(db, receipt_id))


async def list_receipts(db: AsyncSession, status: str, params: PageParams) -> Page[StarsPaymentReceiptOut]:
    """status: "problems" (not delivered and not refunded — what needs an
    admin's eye), "all", or one exact status."""
    query = select(StarsPaymentReceipt)
    if status == "problems":
        query = query.where(StarsPaymentReceipt.status.in_(PROBLEM_STATUSES))
    elif status != "all":
        query = query.where(StarsPaymentReceipt.status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        await db.execute(
            query.order_by(StarsPaymentReceipt.created_at.desc(), StarsPaymentReceipt.id.desc())
            .offset(params.offset).limit(params.page_size)
        )
    ).scalars().all()
    return Page.build([await _to_out(db, r) for r in rows], total, params)


async def count_problems(db: AsyncSession) -> int:
    return (
        await db.execute(
            select(func.count(StarsPaymentReceipt.id)).where(StarsPaymentReceipt.status.in_(PROBLEM_STATUSES))
        )
    ).scalar_one()
