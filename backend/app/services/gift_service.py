from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.gift import Gift, GiftSet
from app.models.notification import Notification
from app.models.user import User
from app.schemas.gift import GiftClaimResult, GiftOut, GiftSetOut
from app.services import collection_service
from app.services.pack_service import grant_bonus_pack_opening
from app.services.wallet_service import credit_coins, lock_user_for_update


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


async def claim_gift(db: AsyncSession, user: User, gift_id: int) -> GiftClaimResult:
    """Opens a pending gift — reward is only granted once the recipient
    explicitly claims it (never on receipt), mirroring opening a pack. Row
    locks the gift before checking claimed_at so two concurrent claim taps
    (e.g. a double-tap) can't both pass the check and deliver twice."""
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

    gift = Gift(gift_set_id=gift_set.id, sender_id=None, recipient_id=recipient.id, message=message, is_admin_gift=True)
    db.add(gift)
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

    now = datetime.now(timezone.utc)
    await db.execute(
        insert(Gift),
        [
            {
                "gift_set_id": gift_set.id, "sender_id": None, "recipient_id": uid,
                "message": message, "is_admin_gift": True, "claimed_at": None,
                "created_at": now, "updated_at": now,
            }
            for uid in user_ids
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
