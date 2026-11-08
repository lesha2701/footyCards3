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
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card_offer import CardOffer, CardOfferPurchase, CardOfferView
from app.models.enums import CardSource, NotificationType
from app.models.notification import Notification
from app.models.player import Player
from app.models.user import User
from app.models.coach import Coach
from app.models.muse import Muse
from app.models.stadium import Stadium
from app.models.town import TownResident
from app.schemas.card_offer import CardOfferAdminIn, CardOfferAdminOut, CardOfferOut, OfferItemOut
from app.schemas.player import PlayerOut
from app.services.wallet_service import lock_user_for_update


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _kind(offer: CardOffer) -> str:
    if offer.coach_id:
        return "coach"
    if offer.stadium_id:
        return "stadium"
    if offer.muse_id:
        return "muse"
    if offer.resident_id:
        return "resident"
    return "player"


def _target(offer: CardOffer):
    return {"coach": offer.coach, "stadium": offer.stadium, "muse": offer.muse,
            "resident": offer.resident}.get(_kind(offer), offer.player)


def _name(offer: CardOffer) -> str:
    target = _target(offer)
    return getattr(target, "display_name", None) or getattr(target, "name", "") or ""


def _item_out(offer: CardOffer) -> Optional[OfferItemOut]:
    kind = _kind(offer)
    if kind == "player":
        return None
    target = _target(offer)
    if kind == "coach":
        from app.services.coach_service import coach_effect_lines

        effects = coach_effect_lines(target)
    elif kind == "stadium":
        from app.services.collection_service import stadium_effect_lines

        effects = stadium_effect_lines(target)
    elif kind == "resident":
        from app.services.town_service import bonus_label

        effects = [x for x in ("Житель города", bonus_label(target.bonus, target.bonus_value)) if x]
    else:
        from app.services.muse_service import effect_label

        effects = [effect_label(target.effect, target.effect_value)]
    rarity = target.rarity.value if hasattr(target.rarity, "value") else str(target.rarity)
    return OfferItemOut(
        kind=kind, id=target.id, name=_name(offer), rarity=rarity, image_path=target.image_path,
        icon=getattr(target, "icon", None), effects=effects,
    )


def _retired(offer: CardOffer) -> bool:
    target = _target(offer)
    return getattr(target, "is_pack_droppable", True) is False


def _live(offer: CardOffer, now: Optional[datetime] = None) -> bool:
    now = now or _now()
    target = _target(offer)
    if not offer.is_active or target is None or not target.is_active:
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
        id=offer.id, kind=_kind(offer), player=PlayerOut.model_validate(offer.player) if offer.player else None,
        item=_item_out(offer), stars_price=offer.stars_price, title=offer.title,
        ends_at=offer.ends_at, stock=offer.stock, left=left, per_user_limit=offer.per_user_limit, bought=bought,
        can_buy=not limit_reached and (left is None or left > 0),
        retired=_retired(offer),
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
    name = _name(offer)
    what = {"coach": "тренера", "stadium": "стадиона", "muse": "музы", "resident": "жителя города"}.get(_kind(offer))
    description = (
        f"Карточка {what} «{name}» в твою коллекцию." if what
        else f"Карточка футболиста {name} ({offer.player.rating}) в твою коллекцию."
    )
    return f"card_offer:{offer.id}", offer.stars_price, f"Карточка: {name}"[:32], description


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
    kind = _kind(offer)
    card_id = None
    if kind == "player":
        card_id = (await create_user_card(db, user.id, offer.player_id, CardSource.stars_purchase, source_ref_id=invoice.id)).id
    elif kind == "coach":
        from app.services.card_creation import create_user_coach_card

        await create_user_coach_card(db, user.id, offer.coach_id, CardSource.stars_purchase, invoice.id)
    elif kind == "stadium":
        from app.services.card_creation import create_user_stadium_card

        await create_user_stadium_card(db, user.id, offer.stadium_id, CardSource.stars_purchase, invoice.id)
    elif kind == "resident":
        from app.services import town_service

        await lock_user_for_update(db, user.id)  # town_service.grant needs the user lock
        await town_service.grant(db, user.id, offer.resident, "stars")
    else:
        from app.services import muse_service

        await lock_user_for_update(db, user.id)  # muse_service.grant needs the user lock
        await muse_service.grant(db, user.id, offer.muse, "stars")
    try:
        async with db.begin_nested():
            db.add(CardOfferPurchase(
                offer_id=offer.id, user_id=user.id, invoice_id=invoice.id, user_card_id=card_id,
                stars_amount=invoice.stars_amount,
            ))
            await db.flush()
    except IntegrityError:
        pass
    offer.sold_count += 1
    db.add(offer)
    # Completing a collection may pay coins — on the locked user row.
    locked = await lock_user_for_update(db, user.id)
    await collection_service.grant_collection_rewards_for_new_cards(
        db, locked, [offer.player_id] if offer.player_id else [],
        collection_ids=await collection_service.staff_collection_ids(
            db, [offer.coach_id] if offer.coach_id else [], [offer.stadium_id] if offer.stadium_id else [],
            [offer.muse_id] if offer.muse_id else [],
        ),
    )
    return {"kind": "card_offer", "user_card_id": card_id}


# --- admin -----------------------------------------------------------------

def _admin_out(offer: CardOffer, stats: Optional[dict] = None) -> CardOfferAdminOut:
    stats = stats or {}
    return CardOfferAdminOut(
        id=offer.id, kind=_kind(offer), player=PlayerOut.model_validate(offer.player) if offer.player else None,
        item=_item_out(offer), stars_price=offer.stars_price, title=offer.title,
        starts_at=offer.starts_at, ends_at=offer.ends_at, stock=offer.stock, per_user_limit=offer.per_user_limit,
        sold_count=offer.sold_count, is_active=offer.is_active, sort_order=offer.sort_order, live=_live(offer),
        announced_at=offer.announced_at, stars_total=stats.get("stars", 0), buyers=stats.get("buyers", 0),
        viewers=stats.get("viewers", 0),
    )


async def _admin_stats(db: AsyncSession, offer_ids: list[int]) -> dict[int, dict]:
    """Per offer: Stars earned, distinct buyers and players who looked."""
    stats: dict[int, dict] = {oid: {} for oid in offer_ids}
    for oid, stars, buyers in (await db.execute(
        select(CardOfferPurchase.offer_id, func.sum(CardOfferPurchase.stars_amount),
               func.count(func.distinct(CardOfferPurchase.user_id)))
        .where(CardOfferPurchase.offer_id.in_(offer_ids or [0])).group_by(CardOfferPurchase.offer_id)
    )).all():
        stats[oid].update(stars=int(stars or 0), buyers=buyers)
    for oid, viewers in (await db.execute(
        select(CardOfferView.offer_id, func.count(CardOfferView.id))
        .where(CardOfferView.offer_id.in_(offer_ids or [0])).group_by(CardOfferView.offer_id)
    )).all():
        stats[oid]["viewers"] = viewers
    return stats


async def admin_list(db: AsyncSession) -> list[CardOfferAdminOut]:
    offers = (await db.execute(
        select(CardOffer).order_by(CardOffer.is_active.desc(), CardOffer.sort_order, CardOffer.id.desc())
    )).unique().scalars().all()
    stats = await _admin_stats(db, [o.id for o in offers])
    return [_admin_out(o, stats.get(o.id)) for o in offers]


async def _apply(db: AsyncSession, offer: CardOffer, data: CardOfferAdminIn) -> None:
    chosen = [(key, model) for key, model in (
        ("player_id", Player), ("coach_id", Coach), ("stadium_id", Stadium), ("muse_id", Muse),
        ("resident_id", TownResident),
    ) if getattr(data, key)]
    if len(chosen) != 1:
        raise ConflictError("Выбери одну карточку: футболиста, тренера, стадион, музу или жителя")
    key, model = chosen[0]
    target = await db.get(model, getattr(data, key))
    if target is None:
        raise NotFoundError("Карточка не найдена")
    if not target.is_active:
        raise ConflictError("Карточка выключена (скрыта из игры) — сначала включи её")
    if data.starts_at and data.ends_at and data.ends_at <= data.starts_at:
        raise ConflictError("Конец продаж должен быть позже начала")
    for field, value in data.model_dump().items():
        setattr(offer, field, value)
    offer.player = target if model is Player else None
    offer.coach = target if model is Coach else None
    offer.stadium = target if model is Stadium else None
    offer.muse = target if model is Muse else None
    offer.resident = target if model is TownResident else None


async def admin_create(db: AsyncSession, data: CardOfferAdminIn) -> CardOfferAdminOut:
    offer = CardOffer(stars_price=data.stars_price)
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
    retired = _retired(offer)
    title = "🔥 Лимитка вернулась в магазин!" if retired else "⭐ Новая карточка в магазине"
    label = f"{offer.player.display_name} · {offer.player.rating}" if offer.player else f"«{_name(offer)}»"
    lines = [f"{label} — за {offer.stars_price} ⭐."]
    if retired:
        lines.append("Из паков она больше не выпадает — купить можно только сейчас.")
    if offer.ends_at:
        lines.append(f"Продажа до {_local(offer.ends_at)}.")
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
    await _notify_all(db, offer, user_ids, title, body, now)
    offer.announced_at = now
    await db.commit()
    return len(user_ids)


def _local(moment: datetime) -> str:
    return ensure_aware(moment).astimezone(ZoneInfo(get_settings().timezone)).strftime("%d.%m %H:%M")


async def _notify_all(db: AsyncSession, offer: CardOffer, user_ids, title: str, body: str, now: datetime) -> None:
    if user_ids:
        await db.execute(insert(Notification), [
            {
                "user_id": uid, "type": NotificationType.admin_message, "title": title, "body": body,
                "related_object_type": "card_offer", "related_object_id": offer.id,
                "is_read": False, "telegram_sent": False, "created_at": now,
            }
            for uid in user_ids
        ])


# ---------------------------------------------------------------------------
# «Осталось 3 часа»: a reminder to those who looked and didn't buy
# ---------------------------------------------------------------------------

REMIND_BEFORE = timedelta(hours=3)


async def mark_viewed(db: AsyncSession, user: User, offer_ids: list[int]) -> None:
    """The player opened «Карты ⭐» with these offers on sale (once each)."""
    wanted = set(offer_ids[:50])
    if not wanted:
        return
    known = set((await db.execute(
        select(CardOfferView.offer_id).where(CardOfferView.user_id == user.id, CardOfferView.offer_id.in_(wanted))
    )).scalars().all())
    existing = set((await db.execute(select(CardOffer.id).where(CardOffer.id.in_(wanted)))).scalars().all())
    for offer_id in (wanted & existing) - known:
        db.add(CardOfferView(offer_id=offer_id, user_id=user.id))
    try:
        await db.commit()
    except IntegrityError:  # two tabs at once — the other request recorded it
        await db.rollback()


async def remind_due(db: AsyncSession) -> int:
    """Offers ending within REMIND_BEFORE: one message to every player who
    viewed it and can still buy it. Once per offer (reminded_at, under the
    offer's row lock) — the bot calls this every few minutes."""
    now = _now()
    due_ids = (await db.execute(
        select(CardOffer.id).where(
            CardOffer.is_active.is_(True), CardOffer.reminded_at.is_(None),
            CardOffer.ends_at.is_not(None), CardOffer.ends_at > now, CardOffer.ends_at <= now + REMIND_BEFORE,
        )
    )).scalars().all()
    sent = 0
    for offer_id in due_ids:
        offer = (await db.execute(
            select(CardOffer).where(CardOffer.id == offer_id).with_for_update()
        )).unique().scalar_one_or_none()
        if offer is None or offer.reminded_at is not None:
            continue
        offer.reminded_at = now
        left = _left(offer)
        if _live(offer, now) and (left is None or left > 0):
            bought = select(CardOfferPurchase.user_id).where(CardOfferPurchase.offer_id == offer.id)
            query = (
                select(CardOfferView.user_id).join(User, User.id == CardOfferView.user_id)
                .where(CardOfferView.offer_id == offer.id, User.is_banned.is_(False), User.bot_blocked.is_(False))
            )
            # A per-player limit of 0 is «unlimited» — buyers may want another.
            if offer.per_user_limit > 0:
                query = query.where(CardOfferView.user_id.not_in(bought))
            user_ids = (await db.execute(query)).scalars().all()
            label = f"{offer.player.display_name} · {offer.player.rating}" if offer.player else f"«{_name(offer)}»"
            body = f"{label} за {offer.stars_price} ⭐ — продажа закончится в {_local(offer.ends_at)}."
            if left is not None:
                body += f" Осталось {left} шт."
            await _notify_all(db, offer, user_ids, "⏳ Осталось меньше 3 часов!", body, now)
            sent += len(user_ids)
        await db.commit()
    return sent
