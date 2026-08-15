import secrets
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.badge import UserBadge
from app.models.card import UserCard
from app.models.coin_package import CoinPackage
from app.models.enums import CardSource, TransactionType, WheelSpinSource
from app.models.gift import Gift, GiftSet
from app.models.pack import Pack, PackOpening, StarsInvoice
from app.models.user import User
from app.models.wheel import WheelPrize, WheelSpin
from app.schemas.badge import BadgeOut
from app.schemas.gift import GiftOut
from app.schemas.pack import OpenedCardOut
from app.schemas.stars import (
    CoinPackageOut,
    StarsCoinResultOut,
    StarsInvoiceCreateOut,
    StarsInvoiceStatusOut,
)
from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut
from app.services import collection_service
from app.services.pack_service import _duplicate_counts_snapshot, get_opening_result, grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, lock_user_for_update

settings = get_settings()


async def list_active_coin_packages(db: AsyncSession) -> list[CoinPackageOut]:
    result = await db.execute(
        select(CoinPackage).where(CoinPackage.is_active.is_(True)).order_by(CoinPackage.sort_order)
    )
    return [CoinPackageOut.model_validate(p) for p in result.scalars().all()]


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

    if invoice.is_wheel_spin:
        # WheelSpin.prize and WheelPrize.pack are lazy="joined", but
        # Pack.rarity_probabilities (needed by PackOut, nested in
        # WheelPrizeOut.pack below) isn't — without this explicit option,
        # serializing a pack-type prize triggers an async lazy-load outside
        # any awaited context (MissingGreenlet).
        spin = await db.get(
            WheelSpin, invoice.wheel_spin_id,
            options=[joinedload(WheelSpin.prize).joinedload(WheelPrize.pack).joinedload(Pack.rarity_probabilities)],
        )
        user = await db.get(User, invoice.user_id)

        pack_result = None
        if spin.pack_opening_id is not None:
            opening = await db.get(PackOpening, spin.pack_opening_id)
            pack_result = await get_opening_result(db, user, opening)

        card_result = None
        if spin.user_card_id is not None:
            card_query = await db.execute(
                select(UserCard).where(UserCard.id == spin.user_card_id).options(joinedload(UserCard.player))
            )
            card = card_query.unique().scalar_one()
            # dup_counts is taken now (well after the card was granted), so it
            # already includes this very card — unlike the pack branch above,
            # which reads a persisted is_new_player flag captured at grant
            # time, a wheel card_rarity prize has no such flag, so "is this
            # still the player's only copy" is recomputed from a fresh
            # snapshot here. This is a reasonable approximation (matches "new"
            # in the overwhelming common case) that can only go stale if the
            # player traded the card away between grant and this poll — not
            # worth a schema migration to fix exactly.
            dup_counts = await _duplicate_counts_snapshot(db, user.id)
            card_result = OpenedCardOut(
                card=card, is_new=dup_counts.get(card.player_id, 1) == 1, duplicate_count=dup_counts.get(card.player_id, 1),
            )

        badge_result = BadgeOut.model_validate(spin.prize.badge) if spin.badge_granted else None

        return StarsInvoiceStatusOut(
            status="completed",
            wheel_result=WheelSpinResultOut(
                prize=WheelPrizeOut.model_validate(spin.prize), new_balance=user.balance,
                pack_result=pack_result, card_result=card_result, badge_result=badge_result,
                duplicate_badge_coins=spin.duplicate_badge_coins,
            ),
        )

    if invoice.gift_set_id is not None:
        gift = await db.get(Gift, invoice.gift_id)
        return StarsInvoiceStatusOut(status="completed", gift_result=GiftOut.model_validate(gift))

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


async def create_coin_invoice(db: AsyncSession, user: User, coin_package_id: int) -> StarsInvoiceCreateOut:
    package = await db.get(CoinPackage, coin_package_id)
    if package is None or not package.is_active:
        raise NotFoundError("Coin package not found")

    # Frozen from the package at invoice-creation time (not re-read at
    # delivery), so an admin editing/deactivating the package mid-purchase
    # can't affect a payment already in flight.
    stars_amount = package.stars_price
    coins = package.coins_amount

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


async def create_gift_invoice(
    db: AsyncSession, user: User, gift_set_id: int, recipient_id: int, message: str | None
) -> StarsInvoiceCreateOut:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    if not gift_set.is_active:
        raise ConflictError("This gift set is not currently available")
    if gift_set.stars_price <= 0:
        raise ConflictError("This gift set cannot be purchased")

    recipient = await db.get(User, recipient_id)
    if recipient is None:
        raise NotFoundError("Recipient not found")
    if recipient.id == user.id:
        raise ConflictError("You can't send a gift to yourself")

    payload_token = secrets.token_urlsafe(16)
    invoice = StarsInvoice(
        user_id=user.id, gift_set_id=gift_set.id, gift_recipient_id=recipient.id, gift_message=message,
        payload_token=payload_token, stars_amount=gift_set.stars_price,
    )
    db.add(invoice)
    await db.flush()

    recipient_label = recipient.username or recipient.first_name or f"игрока #{recipient.id}"
    invoice_link = await _request_telegram_invoice_link(
        payload_token, gift_set.name, f"Подарок для {recipient_label}: {gift_set.description or gift_set.name}",
        gift_set.stars_price,
    )

    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=gift_set.stars_price)


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
    elif invoice.gift_set_id is not None:
        gift_set = await db.get(GiftSet, invoice.gift_set_id)
        if gift_set is None or not gift_set.is_active or gift_set.stars_price != total_amount:
            return False, "This gift set is no longer available"
    return True, ""


async def _grant_pack_badge(db: AsyncSession, user: User, badge_id: int) -> None:
    """Grants ownership of `badge_id` to `user` (idempotent — a repeat
    delivery or a user who already owns it from an earlier purchase is a
    no-op) and auto-equips it as their active badge."""
    existing = await db.execute(
        select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge_id)
    )
    if existing.scalar_one_or_none() is None:
        db.add(UserBadge(user_id=user.id, badge_id=badge_id))
    user.active_badge_id = badge_id
    db.add(user)


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

        if pack.bonus_coins:
            user = await lock_user_for_update(db, user.id)
            await credit_coins(
                db, user, pack.bonus_coins, TransactionType.stars_pack_bonus_coins,
                f"Бонус монет за пак «{pack.name}»",
                related_object_type="stars_invoice", related_object_id=invoice.id,
            )
        if pack.badge_id:
            await _grant_pack_badge(db, user, pack.badge_id)
    elif invoice.gift_set_id is not None:
        gift_set = await db.get(GiftSet, invoice.gift_set_id)
        if gift_set is None or not gift_set.is_active or gift_set.stars_price != total_amount:
            raise ConflictError("This gift set is no longer available")

        gift = Gift(
            gift_set_id=gift_set.id, sender_id=invoice.user_id, recipient_id=invoice.gift_recipient_id,
            message=invoice.gift_message, is_admin_gift=False,
        )
        db.add(gift)
        await db.flush()
        invoice.gift_id = gift.id
    elif invoice.is_wheel_spin:
        # Imported here rather than at module level: wheel_service itself
        # imports _request_telegram_invoice_link from this module at import
        # time, so a top-level `from app.services import wheel_service`
        # here would deadlock the two modules' circular load order
        # depending on which router imports which service first.
        from app.services import wheel_service

        if invoice.stars_amount != total_amount:
            raise ConflictError("Stars amount does not match the invoice")
        # _grant_prize mutates user.balance (coin prizes, duplicate-badge
        # compensation) via credit_coins, which itself does not lock — every
        # other balance-mutating branch in this function locks the user row
        # first (see the pack-bonus-coins and plain-coin-purchase branches
        # above), so this branch does too, to avoid a lost update if two
        # deliveries for the same user race on different invoices.
        user = await lock_user_for_update(db, user.id)
        prize = await wheel_service._roll_prize(db)
        spin_result = await wheel_service._grant_prize(db, user, prize, WheelSpinSource.stars)
        # _grant_prize already flushed a WheelSpin row (it has an id after
        # its own db.flush()) — fetch it back to link the invoice, mirroring
        # how invoice.pack_opening_id/invoice.gift_id are set above.
        spin_row = (
            await db.execute(
                select(WheelSpin).where(WheelSpin.user_id == user.id).order_by(WheelSpin.id.desc()).limit(1)
            )
        ).scalar_one()
        invoice.wheel_spin_id = spin_row.id
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
    if invoice.is_wheel_spin:
        return StarsInvoiceStatusOut(status="completed", wheel_result=spin_result)
    if invoice.gift_set_id is not None:
        await db.refresh(gift)
        return StarsInvoiceStatusOut(status="completed", gift_result=GiftOut.model_validate(gift))
    return StarsInvoiceStatusOut(
        status="completed",
        coin_result=StarsCoinResultOut(coins_credited=invoice.coins_amount, new_balance=user.balance),
    )
