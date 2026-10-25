"""«Карты за звёзды»: footballer cards the admin puts in the shop for
Telegram Stars (CardOffer) — any active card, typically a retired / limited
one (Player.is_pack_droppable = False) back for a short window.

Standard Stars flow (shop_product_service, product "card_offer:<id>"):
availability — window, stock, the player's own limit — is checked at
pre-checkout; delivery never refuses (the player has paid) and is
idempotent by invoice (CardOfferPurchase.invoice_id unique). Two buyers
racing for the very last copy can both get through pre-checkout; both are
delivered, so a sold-out offer may end one or two copies over its stock.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card_offer import CardOffer, CardOfferPurchase
from app.models.enums import CardSource, NotificationType
from app.models.notification import Notification
from app.models.player import Player
from app.models.user import User
from app.schemas.card_offer import CardOfferAdminIn, CardOfferAdminOut, CardOfferOut
from app.schemas.player import PlayerOut
from app.services.wallet_service import lock_user_for_update


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _live(offer: CardOffer, now: Optional[datetime] = None) -> bool:
    now = now or _now()
    if not offer.is_active or not offer.player or not offer.player.is_active:
        return False
    if offer.starts_at and ensure_aware(offer.starts_at) > now:
        return False
    if offer.ends_at and ensure_aware(offer.ends_at) <= now:
        return False
    return True


def _left(offer: CardOffer) -> Optional[int]:
    return None if offer.stock is None else max(0, offer.stock - offer.sold_count)


async def _bought(db: AsyncSession, user_id: int, offer_ids: list[int]) -> dict[int, int]:
    rows = (await db.execute(
        select(CardOfferPurchase.offer_id, func.count(CardOfferPurchase.id))
        .where(CardOfferPurchase.user_id == user_id, CardOfferPurchase.offer_id.in_(offer_ids or [0]))
        .group_by(CardOfferPurchase.offer_id)
    )).all()
    return {oid: n for oid, n in rows}


def _out(offer: CardOffer, bought: int) -> CardOfferOut:
    limit_reached = offer.per_user_limit > 0 and bought >= offer.per_user_limit
    left = _left(offer)
    return CardOfferOut(
        id=offer.id, player=PlayerOut.model_validate(offer.player), stars_price=offer.stars_price, title=offer.title,
        ends_at=offer.ends_at, stock=offer.stock, left=left, per_user_limit=offer.per_user_limit, bought=bought,
        can_buy=not limit_reached and (left is None or left > 0),
        retired=not offer.player.is_pack_droppable,
    )


async def list_live(db: AsyncSession, user: User) -> list[CardOfferOut]:
    """Offers on sale right now (sold-out ones stay listed, marked)."""
    offers = (await db.execute(
        select(CardOffer).where(CardOffer.is_active.is_(True)).order_by(CardOffer.sort_order, CardOffer.id.desc())
    )).unique().scalars().all()
    now = _now()
    live = [o for o in offers if _live(o, now)]
    bought = await _bought(db, user.id, [o.id for o in live])
    return [_out(o, bought.get(o.id, 0)) for o in live]


async def _check(db: AsyncSession, offer: Optional[CardOffer], user_id: int, stars: Optional[int] = None) -> Optional[str]:
    """Why this purchase can't go ahead now (None = it can)."""
    if offer is None or not _live(offer):
        return "Это предложение уже закончилось"
    if stars is not None and stars != offer.stars_price:
        return "Цена изменилась — открой покупку заново"
    left = _left(offer)
    if left is not None and left <= 0:
        return "Все карточки уже раскупили"
    if offer.per_user_limit > 0:
        bought = (await _bought(db, user_id, [offer.id])).get(offer.id, 0)
        if bought >= offer.per_user_limit:
            return "Ты уже купил максимум этих карточек"
    return None


async def stars_order(db: AsyncSession, user: User, offer_id: int) -> tuple[str, int, str, str]:
    offer = await db.get(CardOffer, offer_id)
    reason = await _check(db, offer, user.id)
    if reason:
        raise ConflictError(reason)
    name = offer.player.display_name
    return (
        f"card_offer:{offer.id}", offer.stars_price, f"Карточка: {name}"[:32],
        f"Карточка футболиста {name} ({offer.player.rating}) в твою коллекцию.",
    )


async def validate_stars(db: AsyncSession, user_id: int, offer_id: int, stars_amount: int) -> tuple[bool, str]:
    reason = await _check(db, await db.get(CardOffer, offer_id), user_id, stars_amount)
    return (reason is None), (reason or "")


async def deliver_stars(db: AsyncSession, user: User, invoice) -> dict:
    """Already paid: never refuses. The caller (deliver_payment) holds the
    invoice lock and commits."""
    from app.services import collection_service
    from app.services.card_creation import create_user_card

    _, _, arg = invoice.shop_product.partition(":")
    offer = (await db.execute(
        select(CardOffer).where(CardOffer.id == int(arg)).with_for_update(of=CardOffer)
        .execution_options(populate_existing=True)
    )).unique().scalar_one_or_none()
    if offer is None:
        raise NotFoundError("Предложение не найдено")
    existing = (await db.execute(
        select(CardOfferPurchase).where(CardOfferPurchase.invoice_id == invoice.id)
    )).scalar_one_or_none()
    if existing is not None:
        return {"kind": "card_offer", "user_card_id": existing.user_card_id}
    card = await create_user_card(db, user.id, offer.player_id, CardSource.stars_purchase, source_ref_id=invoice.id)
    try:
        async with db.begin_nested():
            db.add(CardOfferPurchase(
                offer_id=offer.id, user_id=user.id, invoice_id=invoice.id, user_card_id=card.id,
                stars_amount=invoice.stars_amount,
            ))
            await db.flush()
    except IntegrityError:
        pass
    offer.sold_count += 1
    db.add(offer)
    # Completing a collection may pay coins — on the locked user row.
    locked = await lock_user_for_update(db, user.id)
    await collection_service.grant_collection_rewards_for_new_cards(db, locked, [offer.player_id])
    return {"kind": "card_offer", "user_card_id": card.id}


# --- admin -----------------------------------------------------------------

def _admin_out(offer: CardOffer) -> CardOfferAdminOut:
    return CardOfferAdminOut(
        id=offer.id, player=PlayerOut.model_validate(offer.player), stars_price=offer.stars_price, title=offer.title,
        starts_at=offer.starts_at, ends_at=offer.ends_at, stock=offer.stock, per_user_limit=offer.per_user_limit,
        sold_count=offer.sold_count, is_active=offer.is_active, sort_order=offer.sort_order, live=_live(offer),
        announced_at=offer.announced_at,
    )


async def admin_list(db: AsyncSession) -> list[CardOfferAdminOut]:
    offers = (await db.execute(
        select(CardOffer).order_by(CardOffer.is_active.desc(), CardOffer.sort_order, CardOffer.id.desc())
    )).unique().scalars().all()
    return [_admin_out(o) for o in offers]


async def _apply(db: AsyncSession, offer: CardOffer, data: CardOfferAdminIn) -> None:
    player = await db.get(Player, data.player_id)
    if player is None:
        raise NotFoundError("Карточка не найдена")
    if not player.is_active:
        raise ConflictError("Карточка выключена (скрыта из игры) — сначала включи её")
    if data.starts_at and data.ends_at and data.ends_at <= data.starts_at:
        raise ConflictError("Конец продаж должен быть позже начала")
    for key, value in data.model_dump().items():
        setattr(offer, key, value)
    offer.player = player


async def admin_create(db: AsyncSession, data: CardOfferAdminIn) -> CardOfferAdminOut:
    offer = CardOffer(player_id=data.player_id, stars_price=data.stars_price)
    await _apply(db, offer, data)
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return _admin_out(offer)


async def admin_update(db: AsyncSession, offer_id: int, data: CardOfferAdminIn) -> CardOfferAdminOut:
    offer = await db.get(CardOffer, offer_id)
    if offer is None:
        raise NotFoundError("Предложение не найдено")
    await _apply(db, offer, data)
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return _admin_out(offer)


async def admin_delete(db: AsyncSession, offer_id: int) -> None:
    """Only offers nobody bought yet — sold ones are switched off instead,
    so the purchase history stays."""
    offer = await db.get(CardOffer, offer_id)
    if offer is None:
        raise NotFoundError("Предложение не найдено")
    if offer.sold_count:
        raise ConflictError("Эту карточку уже покупали — выключи предложение вместо удаления")
    await db.delete(offer)
    await db.commit()


def _announce_text(offer: CardOffer) -> tuple[str, str]:
    player = offer.player
    retired = player.is_pack_droppable is False
    title = "🔥 Лимитка вернулась в магазин!" if retired else "⭐ Новая карточка в магазине"
    lines = [f"{player.display_name} · {player.rating} — за {offer.stars_price} ⭐."]
    if retired:
        lines.append("Из паков она больше не выпадает — купить можно только сейчас.")
    if offer.ends_at:
        lines.append(f"Продажа до {ensure_aware(offer.ends_at).strftime('%d.%m %H:%M')} UTC.")
    if offer.stock:
        lines.append(f"Всего {offer.stock} шт.")
    return title, " ".join(lines)


async def admin_announce(db: AsyncSession, offer_id: int) -> int:
    """«Разослать игрокам»: one bot message per player about a live offer,
    once per offer (announced_at, decided under the offer's row lock)."""
    offer = (await db.execute(select(CardOffer).where(CardOffer.id == offer_id).with_for_update())).unique().scalar_one_or_none()
    if offer is None:
        raise NotFoundError("Предложение не найдено")
    if offer.announced_at is not None:
        raise ConflictError("Об этой карточке уже разослали")
    if not _live(offer):
        raise ConflictError("Предложение сейчас не в продаже — сначала включи его")
    title, body = _announce_text(offer)
    user_ids = (
        await db.execute(select(User.id).where(User.is_banned.is_(False), User.bot_blocked.is_(False)))
    ).scalars().all()
    now = _now()
    if user_ids:
        await db.execute(insert(Notification), [
            {
                "user_id": uid, "type": NotificationType.admin_message, "title": title, "body": body,
                "related_object_type": "card_offer", "related_object_id": offer.id,
                "is_read": False, "telegram_sent": False, "created_at": now,
            }
            for uid in user_ids
        ])
    offer.announced_at = now
    await db.commit()
    return len(user_ids)
