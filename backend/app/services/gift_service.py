from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import CardSource, GiftKind, NotificationType, TransactionType
from app.models.gift import Gift, GiftSet
from app.models.notification import Notification
from app.models.user import User
from app.schemas.gift import GiftClaimResult, GiftOut, GiftPurchaseResult, GiftSetOut
from app.services import collection_service
from app.services.pack_service import grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


async def list_active_gift_sets(db: AsyncSession) -> list[GiftSetOut]:
    result = await db.execute(select(GiftSet).where(GiftSet.is_active.is_(True)).order_by(GiftSet.sort_order))
    return [GiftSetOut.model_validate(g) for g in result.scalars().all()]


async def list_my_gifts(db: AsyncSession, user: User) -> list[GiftOut]:
    result = await db.execute(
        select(Gift)
        .where(Gift.recipient_id == user.id)
        .order_by(Gift.claimed_at.is_not(None), Gift.created_at.desc())
    )
    return [GiftOut.model_validate(g) for g in result.scalars().all()]


async def reserve_gift_serial_numbers(db: AsyncSession, gift_set: GiftSet, count: int = 1) -> Optional[int]:
    """Atomically reserves `count` consecutive serial numbers on a
    collectible gift_set and returns the first one — None for a bundle,
    which is never numbered. Row-locks gift_set so concurrent mints (two
    purchases, or a purchase racing an admin broadcast) can't hand out the
    same number. Enforces max_supply; raises rather than partially
    fulfilling an over-capacity request."""
    if gift_set.kind != GiftKind.collectible:
        return None
    result = await db.execute(
        select(GiftSet).where(GiftSet.id == gift_set.id).with_for_update().execution_options(populate_existing=True)
    )
    locked = result.scalar_one()
    start = locked.next_serial_number
    end = start + count - 1
    if locked.max_supply is not None and end > locked.max_supply:
        remaining = max(0, locked.max_supply - start + 1)
        raise ConflictError(f"Недостаточно тиража: осталось {remaining}, а нужно {count}")
    locked.next_serial_number = end + 1
    db.add(locked)
    return start


async def claim_gift(db: AsyncSession, user: User, gift_id: int) -> GiftClaimResult:
    """Opens a pending gift — reward is only granted once the recipient
    explicitly claims it (never on receipt), mirroring opening a pack. Row
    locks the gift before checking claimed_at so two concurrent claim taps
    (e.g. a double-tap) can't both pass the check and deliver twice.

    Both gift kinds share this exact reward logic: a collectible with no
    configured coins_amount/pack_id just claims with nothing granted (the
    common case — the row's existence is its own reward); one with a prize
    configured grants it exactly like a bundle does."""
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.claimed_at is not None:
        raise ConflictError("This gift was already claimed")

    gift_set = gift.gift_set

    pack_result = None
    if gift_set.pack_id is not None:
        granted = await grant_bonus_pack_opening(
            db, user, gift_set.pack_id, idempotency_prefix=f"gift-{gift.id}", source=CardSource.gift,
        )
        if granted is not None:
            granted.collection_rewards = await collection_service.grant_collection_rewards_for_new_cards(
                db, user, [item.card.player.id for item in granted.cards]
            )
            gift.pack_opening_id = granted.opening_id
            pack_result = granted

    if gift_set.coins_amount:
        user = await lock_user_for_update(db, user.id)
        await credit_coins(
            db, user, gift_set.coins_amount, TransactionType.gift_coins,
            f"Подарок «{gift_set.name}»", related_object_type="gift", related_object_id=gift.id,
        )

    gift.claimed_at = datetime.now(timezone.utc)
    db.add(gift)
    await db.commit()
    await db.refresh(user)
    await db.refresh(gift)

    if pack_result is not None:
        pack_result.new_balance = user.balance

    return GiftClaimResult(
        gift=GiftOut.model_validate(gift), pack_result=pack_result,
        coins_credited=gift_set.coins_amount, new_balance=user.balance,
    )


async def admin_send_gift_to_user(db: AsyncSession, gift_set_id: int, user_id: int, message: Optional[str]) -> GiftOut:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    recipient = await db.get(User, user_id)
    if recipient is None:
        raise NotFoundError("User not found")

    serial_number = await reserve_gift_serial_numbers(db, gift_set)

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=None, recipient_id=recipient.id, message=message,
        is_admin_gift=True, serial_number=serial_number,
    )
    db.add(gift)
    db.add(
        Notification(
            user_id=recipient.id, type=NotificationType.admin_message,
            title="🎁 Подарок!", body=message or "Тебе подарок в приложении — открой и забери!",
        )
    )
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)


async def admin_broadcast_gift(db: AsyncSession, gift_set_id: int, message: Optional[str]) -> int:
    """Grants gift_set_id free to every registered user (a holiday-style
    giveaway) via a single bulk INSERT rather than one ORM object per user.

    Also queues a real Telegram notification per recipient (same
    Notification table + notifier.py delivery path as
    broadcast_service.send_update_broadcast), so the bulk grant doesn't sit
    silently in-app — recipients are paced at notifier.py's rate limit
    rather than pinged all at once."""
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")

    user_ids = (await db.execute(select(User.id))).scalars().all()
    if not user_ids:
        return 0

    start_serial = await reserve_gift_serial_numbers(db, gift_set, count=len(user_ids))

    now = datetime.now(timezone.utc)
    await db.execute(
        insert(Gift),
        [
            {
                "gift_set_id": gift_set.id, "sender_id": None, "recipient_id": uid,
                "message": message, "is_admin_gift": True, "claimed_at": None,
                "serial_number": (start_serial + i) if start_serial is not None else None,
                "created_at": now, "updated_at": now,
            }
            for i, uid in enumerate(user_ids)
        ],
    )
    await db.execute(
        insert(Notification),
        [
            {
                "user_id": uid, "type": NotificationType.admin_message,
                "title": "🎁 Подарок!", "body": message or "Тебе подарок в приложении — открой и забери!",
                "is_read": False, "telegram_sent": False, "created_at": now,
            }
            for uid in user_ids
        ],
    )
    await db.commit()
    return len(user_ids)


async def buy_collectible_with_coins(
    db: AsyncSession, buyer: User, gift_set_id: int, recipient_id: int, message: Optional[str],
) -> GiftPurchaseResult:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    if not gift_set.is_active:
        raise ConflictError("This gift is not currently available")
    if gift_set.kind != GiftKind.collectible:
        raise ConflictError("This gift can only be bought with Stars")
    if gift_set.coins_price <= 0:
        raise ConflictError("This gift cannot be bought with coins")

    recipient = await db.get(User, recipient_id)
    if recipient is None:
        raise NotFoundError("Recipient not found")

    buyer = await lock_user_for_update(db, buyer.id)
    serial_number = await reserve_gift_serial_numbers(db, gift_set)
    await debit_coins(
        db, buyer, gift_set.coins_price, TransactionType.gift_purchase_coins,
        f"Подарок «{gift_set.name}»", related_object_type="gift_set", related_object_id=gift_set.id,
    )

    gift = Gift(
        gift_set_id=gift_set.id, sender_id=buyer.id, recipient_id=recipient.id, message=message,
        is_admin_gift=False, serial_number=serial_number,
    )
    db.add(gift)
    await db.commit()
    await db.refresh(buyer)
    await db.refresh(gift)

    return GiftPurchaseResult(gift=GiftOut.model_validate(gift), new_balance=buyer.balance)


async def set_gift_pinned(db: AsyncSession, user: User, gift_id: int, pinned: bool) -> GiftOut:
    result = await db.execute(
        select(Gift).where(Gift.id == gift_id).with_for_update(of=Gift).execution_options(populate_existing=True)
    )
    gift = result.scalar_one_or_none()
    if gift is None or gift.recipient_id != user.id:
        raise NotFoundError("Gift not found")
    if gift.gift_set.kind != GiftKind.collectible:
        raise ConflictError("Only collectible gifts can be pinned")
    if gift.claimed_at is None:
        raise ConflictError("This gift hasn't been claimed yet")

    if pinned and not gift.is_pinned:
        pinned_count = (
            await db.execute(
                select(func.count()).select_from(Gift).where(Gift.recipient_id == user.id, Gift.is_pinned.is_(True))
            )
        ).scalar_one()
        if pinned_count >= 3:
            raise ConflictError("You can only pin up to 3 gifts — unpin one first")
        gift.is_pinned = True
        gift.pinned_at = datetime.now(timezone.utc)
    elif not pinned:
        gift.is_pinned = False
        gift.pinned_at = None

    db.add(gift)
    await db.commit()
    await db.refresh(gift)
    return GiftOut.model_validate(gift)
