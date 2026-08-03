import secrets
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import CardSource, TransactionType
from app.models.pack import Pack, PackOpening, StarsInvoice
from app.models.user import User
from app.schemas.stars import (
    StarsCoinRateOut,
    StarsCoinResultOut,
    StarsInvoiceCreateOut,
    StarsInvoiceStatusOut,
)
from app.services import collection_service
from app.services.game_config_service import get_config
from app.services.pack_service import get_opening_result, grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, lock_user_for_update

settings = get_settings()


def coins_for_stars(stars_amount: int, rate: int, bulk_threshold: int, bulk_bonus_pct: float) -> int:
    coins = stars_amount * rate
    if stars_amount >= bulk_threshold:
        coins = round(coins * (1 + bulk_bonus_pct))
    return coins


async def get_coin_rate(db: AsyncSession) -> StarsCoinRateOut:
    config = await get_config(db)
    return StarsCoinRateOut(
        stars_to_coins_rate=config.stars_to_coins_rate,
        stars_bulk_threshold=config.stars_bulk_threshold,
        stars_bulk_bonus_pct=float(config.stars_bulk_bonus_pct),
    )


async def _get_invoice_or_404(db: AsyncSession, payload_token: str) -> StarsInvoice:
    result = await db.execute(select(StarsInvoice).where(StarsInvoice.payload_token == payload_token))
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


async def _delivered_result(db: AsyncSession, invoice: StarsInvoice) -> StarsInvoiceStatusOut:
    """Reconstructs the completed result for an already-delivered invoice —
    either the granted pack or the coins credited, whichever this was for."""
    if invoice.pack_id is not None:
        user = await db.get(User, invoice.user_id)
        opening = await db.get(PackOpening, invoice.pack_opening_id)
        return StarsInvoiceStatusOut(status="completed", result=await get_opening_result(db, user, opening))

    user = await db.get(User, invoice.user_id)
    return StarsInvoiceStatusOut(
        status="completed",
        coin_result=StarsCoinResultOut(coins_credited=invoice.coins_amount, new_balance=user.balance),
    )


async def _request_telegram_invoice_link(payload_token: str, title: str, description: str, stars_amount: int) -> str:
    """Calls the Bot API to mint an invoice link. Split out from the create_*
    functions so tests can monkeypatch this one Telegram-calling function
    instead of mocking httpx (mirrors telegram_service's
    check_channel_membership)."""
    body = {
        "title": title[:32],
        "description": description[:255],
        "payload": payload_token,
        "provider_token": "",
        "currency": "XTR",
        "prices": [{"label": title[:32], "amount": stars_amount}],
    }
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/createInvoiceLink"
    async with httpx.AsyncClient(timeout=10, proxy=settings.telegram_proxy_url or None) as client:
        resp = await client.post(url, json=body)
    data = resp.json()
    if not data.get("ok"):
        raise ConflictError(f"Failed to create Telegram invoice: {data.get('description', 'unknown error')}")
    return data["result"]


async def create_invoice(db: AsyncSession, user: User, pack_id: int) -> StarsInvoiceCreateOut:
    pack = await db.get(Pack, pack_id)
    if not pack:
        raise NotFoundError("Pack not found")
    if pack.stars_price is None:
        raise ConflictError("This pack is not purchasable with Telegram Stars")
    if not pack.is_active:
        raise ConflictError("This pack is not currently available")

    payload_token = secrets.token_urlsafe(16)
    invoice = StarsInvoice(
        user_id=user.id, pack_id=pack.id, payload_token=payload_token, stars_amount=pack.stars_price,
    )
    db.add(invoice)
    await db.flush()

    invoice_link = await _request_telegram_invoice_link(
        payload_token, pack.name, pack.description or pack.name, pack.stars_price,
    )

    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=pack.stars_price)


async def create_coin_invoice(db: AsyncSession, user: User, stars_amount: int) -> StarsInvoiceCreateOut:
    if stars_amount <= 0:
        raise ConflictError("stars_amount must be positive")

    config = await get_config(db)
    coins = coins_for_stars(
        stars_amount, config.stars_to_coins_rate, config.stars_bulk_threshold, float(config.stars_bulk_bonus_pct)
    )

    payload_token = secrets.token_urlsafe(16)
    invoice = StarsInvoice(
        user_id=user.id, pack_id=None, coins_amount=coins, payload_token=payload_token, stars_amount=stars_amount,
    )
    db.add(invoice)
    await db.flush()

    invoice_link = await _request_telegram_invoice_link(
        payload_token, "Монеты VICTOR FC", f"{coins} игровых монет за {stars_amount} ⭐", stars_amount,
    )

    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=stars_amount)


async def get_invoice_status(db: AsyncSession, user: User, payload_token: str) -> StarsInvoiceStatusOut:
    invoice = await _get_invoice_or_404(db, payload_token)
    if invoice.user_id != user.id:
        raise NotFoundError("Invoice not found")

    if invoice.completed_at is None:
        return StarsInvoiceStatusOut(status="pending")

    return await _delivered_result(db, invoice)


async def validate_pre_checkout(db: AsyncSession, payload_token: str, total_amount: int) -> tuple[bool, str]:
    """Answers Telegram's pre_checkout_query: is this order still good to
    charge? Called by the bot, which must respond within Telegram's 10s
    deadline — keep this cheap (no Bot API calls, just DB reads)."""
    result = await db.execute(select(StarsInvoice).where(StarsInvoice.payload_token == payload_token))
    invoice = result.scalar_one_or_none()
    if invoice is None:
        return False, "Unknown order"
    if invoice.completed_at is not None:
        return False, "This order was already paid"
    if invoice.stars_amount != total_amount:
        return False, "Price mismatch"

    if invoice.pack_id is not None:
        pack = await db.get(Pack, invoice.pack_id)
        if pack is None or not pack.is_active or pack.stars_price != total_amount:
            return False, "This pack is no longer available"
    return True, ""


async def deliver_payment(
    db: AsyncSession, payload_token: str, telegram_user_id: int, telegram_payment_charge_id: str, total_amount: int
) -> StarsInvoiceStatusOut:
    """Grants the pack or credits the coins for a completed Telegram Stars
    payment. Called by the bot after it receives `successful_payment`.
    Idempotent: if this invoice was already delivered (e.g. Telegram
    redelivered the update), returns the same result instead of delivering
    twice.

    Row-locks the invoice before checking `completed_at` — without it, two
    concurrent deliveries for the same payload_token (a redelivered update
    racing the original) could both pass the check before either commits and
    deliver twice."""
    result = await db.execute(
        select(StarsInvoice).where(StarsInvoice.payload_token == payload_token).with_for_update()
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise NotFoundError("Invoice not found")

    if invoice.completed_at is not None:
        return await _delivered_result(db, invoice)

    result = await db.execute(select(User).where(User.telegram_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    if user.id != invoice.user_id:
        raise ConflictError("This payment does not belong to the invoice's original user")

    if invoice.pack_id is not None:
        pack = await db.get(Pack, invoice.pack_id)
        if pack is None or pack.stars_price != total_amount:
            raise ConflictError("Stars amount does not match the pack price")

        # payload_token (our own short, bounded id), not the Telegram charge
        # id — real charge ids can run well past 128 characters, which
        # overflows PackOpening.idempotency_key (varchar(128)) once
        # grant_bonus_pack_opening appends its own "-<timestamp>" suffix. The
        # actual once-only guarantee for this payment still comes from the
        # row lock + completed_at check above and
        # StarsInvoice.telegram_payment_charge_id's unique constraint.
        granted = await grant_bonus_pack_opening(
            db, user, pack.id, idempotency_prefix=f"stars-{payload_token}", source=CardSource.stars_purchase,
        )
        if granted is None:
            raise NotFoundError("Pack not found")

        granted.collection_rewards = await collection_service.grant_collection_rewards_for_new_cards(
            db, user, [item.card.player.id for item in granted.cards]
        )
        invoice.pack_opening_id = granted.opening_id
    else:
        if invoice.stars_amount != total_amount:
            raise ConflictError("Stars amount does not match the invoice")
        user = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, user, invoice.coins_amount, TransactionType.stars_coin_purchase,
            f"Покупка {invoice.coins_amount} монет за {invoice.stars_amount} ⭐",
            related_object_type="stars_invoice", related_object_id=invoice.id,
        )

    invoice.telegram_payment_charge_id = telegram_payment_charge_id
    invoice.completed_at = datetime.now(timezone.utc)
    db.add(invoice)

    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent deliveries raced on the same charge id (e.g. the bot
        # redelivered the update while the first call was still committing).
        await db.rollback()
        refreshed = await _get_invoice_or_404(db, payload_token)
        if refreshed.completed_at is not None:
            return await _delivered_result(db, refreshed)
        raise

    await db.refresh(user)
    if invoice.pack_id is not None:
        granted.new_balance = user.balance
        return StarsInvoiceStatusOut(status="completed", result=granted)
    return StarsInvoiceStatusOut(
        status="completed",
        coin_result=StarsCoinResultOut(coins_credited=invoice.coins_amount, new_balance=user.balance),
    )
