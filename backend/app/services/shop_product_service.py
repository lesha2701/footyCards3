"""Telegram Stars products of the monetization features, all on one
StarsInvoice column (`shop_product`) so they share the standard flow:
invoice (price frozen) → pre-checkout (availability) → receipt → delivery
(stars_payment_service.deliver_payment → `deliver` here, under the
invoice's row lock) → admin Магазин → Платежи Stars.

Keys: "calendar_catchup:<YYYY-MM-DD>", "cosmetic:<id>", "club_pass",
"club_pass_renewal" (created by delivery for each auto-renewal),
"season_premium:<season_id>", "starter_offer",
"club_emblem:<club_id>:<item_id>", "club_donation:<club_id>:<coins>",
"club_stars:<club_id>", "muse_accessory:<user_muse_id>:<accessory_id>"."""
import secrets
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.monetization import ShopInvoiceStatusOut
from app.schemas.stars import StarsInvoiceCreateOut

# Telegram's only supported subscription period: 30 days.
SUBSCRIPTION_PERIOD_SECONDS = 2592000

LABELS = {
    "calendar_catchup": "Календарь: догнать день",
    "cosmetic": "Косметика",
    "club_pass": "Клубный абонемент",
    "club_pass_renewal": "Клубный абонемент: продление",
    "season_premium": "Сезонный пропуск",
    "starter_offer": "Стартовое предложение",
    "artifact": "Артефакты",
    "equipment": "Экипировка",
    "muse_accessory": "Подарки музам",
    "club_emblem": "Эмблема клуба",
    "club_donation": "Казна клуба",
    "club_stars": "Звёзды клуба",
}


def _split(product: str) -> tuple[str, str]:
    kind, _, arg = product.partition(":")
    return kind, arg


def label(product: str) -> str:
    return LABELS.get(_split(product)[0], "Другое")


async def create_invoice(
    db: AsyncSession, user: User, product: str, stars: int, title: str, description: str,
) -> StarsInvoiceCreateOut:
    """`description` is what Telegram shows on the payment sheet — callers
    list exactly what the purchase contains (legal: shown before paying)."""
    from app.services.stars_payment_service import _request_telegram_invoice_link

    token = secrets.token_urlsafe(16)
    db.add(StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, shop_product=product))
    await db.flush()
    if product == "club_pass":
        link = await _request_telegram_invoice_link(
            token, title, description, stars, subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
        )
    else:
        link = await _request_telegram_invoice_link(token, title, description, stars)
    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=link, payload_token=token, stars_amount=stars)


async def get_status(db: AsyncSession, user: User, payload_token: str) -> ShopInvoiceStatusOut:
    invoice = (await db.execute(
        select(StarsInvoice).where(StarsInvoice.payload_token == payload_token)
    )).scalar_one_or_none()
    if invoice is None or invoice.user_id != user.id or not invoice.shop_product:
        raise NotFoundError("Invoice not found")
    return ShopInvoiceStatusOut(
        status="completed" if invoice.completed_at is not None else "pending", product=invoice.shop_product,
    )


async def validate(db: AsyncSession, invoice: StarsInvoice) -> tuple[bool, str]:
    from app.services import (
        club_pass_service,
        cosmetic_service,
        daily_reward_service,
        season_pass_service,
        starter_offer_service,
    )

    kind, arg = _split(invoice.shop_product)
    if kind == "calendar_catchup":
        return await daily_reward_service.validate_stars(db, invoice.user_id, date.fromisoformat(arg), invoice.stars_amount)
    if kind == "cosmetic":
        return await cosmetic_service.validate_stars(db, invoice.user_id, int(arg), invoice.stars_amount)
    if kind == "club_pass":
        return await club_pass_service.validate_stars(db, invoice.user_id, invoice.stars_amount)
    if kind == "season_premium":
        return await season_pass_service.validate_stars(db, invoice.user_id, int(arg), invoice.stars_amount)
    if kind == "starter_offer":
        return await starter_offer_service.validate_stars(db, invoice.user_id, invoice.stars_amount)
    if kind == "artifact":
        from app.services import artifact_service

        return await artifact_service.validate_stars(db, invoice.user_id, int(arg), invoice.stars_amount)
    if kind == "equipment":
        from app.services import equipment_service

        return await equipment_service.validate_stars(db, invoice.user_id, int(arg), invoice.stars_amount)
    if kind == "muse_accessory":
        from app.services import muse_service

        return await muse_service.validate_stars(db, invoice.user_id, arg, invoice.stars_amount)
    if kind == "club_emblem":
        from app.services import club_emblem_service

        return await club_emblem_service.validate_stars(db, invoice.user_id, arg, invoice.stars_amount)
    if kind == "club_donation":
        from app.services import club_treasury_service

        return await club_treasury_service.validate_stars(db, invoice.user_id, arg, invoice.stars_amount)
    if kind == "club_stars":
        from app.services import club_treasury_service

        return await club_treasury_service.validate_club_stars(db, invoice.user_id, arg)
    return False, "Unknown order"


async def deliver(
    db: AsyncSession, user: User, invoice: StarsInvoice, charge_id: str,
    subscription_expiration: Optional[int] = None,
) -> dict:
    """Called by deliver_payment under the invoice row lock; the payment is
    already taken, so delivery never refuses on soft limits. The caller
    commits."""
    from app.services import (
        club_pass_service,
        cosmetic_service,
        daily_reward_service,
        season_pass_service,
        starter_offer_service,
    )

    kind, arg = _split(invoice.shop_product)
    if kind == "calendar_catchup":
        return await daily_reward_service.deliver_stars(db, user, date.fromisoformat(arg))
    if kind == "cosmetic":
        return await cosmetic_service.deliver_stars(db, user, int(arg))
    if kind in ("club_pass", "club_pass_renewal"):
        return await club_pass_service.deliver_payment(
            db, user, charge_id, subscription_expiration, is_renewal=kind == "club_pass_renewal",
        )
    if kind == "season_premium":
        return await season_pass_service.deliver_stars(db, user, int(arg))
    if kind == "starter_offer":
        return await starter_offer_service.deliver_stars(db, user, invoice)
    if kind == "artifact":
        from app.services import artifact_service

        return await artifact_service.deliver_stars(db, user, int(arg))
    if kind == "equipment":
        from app.services import equipment_service

        return await equipment_service.deliver_stars(db, user, int(arg))
    if kind == "muse_accessory":
        from app.services import muse_service

        return await muse_service.deliver_stars(db, user, arg)
    if kind == "club_emblem":
        from app.services import club_emblem_service

        return await club_emblem_service.deliver_stars(db, user, arg)
    if kind == "club_donation":
        from app.services import club_treasury_service

        return await club_treasury_service.deliver_stars(db, user, invoice)
    if kind == "club_stars":
        from app.services import club_treasury_service

        return await club_treasury_service.deliver_club_stars(db, user, invoice)
    raise NotFoundError("Unknown product")
