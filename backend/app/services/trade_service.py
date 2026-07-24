from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, InsufficientBalanceError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import NotificationType, TradeCardSide, TradeStatus, TransactionType
from app.models.trade import TradeOffer, TradeOfferCard
from app.models.user import User
from app.schemas.trade import TradeCreateRequest, TradeOfferOut
from app.services import task_service
from app.services.notification_service import notify
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

TRADE_EXPIRY_HOURS = 24


async def hydrate_offer(db: AsyncSession, offer: TradeOffer) -> TradeOfferOut:
    cards_result = await db.execute(
        select(TradeOfferCard).where(TradeOfferCard.trade_offer_id == offer.id)
    )
    trade_cards = cards_result.scalars().all()
    card_ids = [tc.user_card_id for tc in trade_cards]
    offered_ids = {tc.user_card_id for tc in trade_cards if tc.side == TradeCardSide.offered}

    cards_by_id = {}
    if card_ids:
        cards_result2 = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )
        cards_by_id = {c.id: c for c in cards_result2.unique().scalars().all()}

    offered_cards = [cards_by_id[i] for i in card_ids if i in offered_ids and i in cards_by_id]
    requested_cards = [cards_by_id[i] for i in card_ids if i not in offered_ids and i in cards_by_id]

    sender = await db.get(User, offer.sender_id)
    receiver = await db.get(User, offer.receiver_id)

    return TradeOfferOut(
        id=offer.id,
        sender=sender,
        receiver=receiver,
        status=offer.status,
        sender_coins=offer.sender_coins,
        receiver_coins=offer.receiver_coins,
        message=offer.message,
        offered_cards=offered_cards,
        requested_cards=requested_cards,
        expires_at=offer.expires_at,
        resolved_at=offer.resolved_at,
        created_at=offer.created_at,
    )


async def unlock_trade_cards(db: AsyncSession, offer_id: int) -> None:
    result = await db.execute(select(TradeOfferCard).where(TradeOfferCard.trade_offer_id == offer_id))
    trade_cards = result.scalars().all()
    card_ids = [tc.user_card_id for tc in trade_cards]
    if not card_ids:
        return
    cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(card_ids)))
    for card in cards_result.scalars().all():
        card.is_locked_in_trade = False
        db.add(card)


async def _expire_if_needed(db: AsyncSession, offer: TradeOffer) -> TradeOffer:
    if offer.status == TradeStatus.pending and ensure_aware(offer.expires_at) <= datetime.now(timezone.utc):
        offer.status = TradeStatus.expired
        offer.resolved_at = datetime.now(timezone.utc)
        await unlock_trade_cards(db, offer.id)
        await notify(
            db, offer.sender_id, NotificationType.trade_offer_expired,
            "Обмен истёк", "Ваше предложение обмена истекло, карточки разблокированы.",
            "trade_offer", offer.id,
        )
        await notify(
            db, offer.receiver_id, NotificationType.trade_offer_expired,
            "Обмен истёк", "Входящее предложение обмена истекло.",
            "trade_offer", offer.id,
        )
        db.add(offer)
        await db.commit()
        await db.refresh(offer)
    return offer


async def expire_stale_trades(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    result = await db.execute(select(TradeOffer).where(TradeOffer.status == TradeStatus.pending, TradeOffer.expires_at <= now))
    stale = result.scalars().all()
    for offer in stale:
        await _expire_if_needed(db, offer)
    return len(stale)


async def _find_receiver(db: AsyncSession, payload: TradeCreateRequest) -> User:
    if payload.receiver_id:
        receiver = await db.get(User, payload.receiver_id)
    else:
        result = await db.execute(select(User).where(User.username == payload.receiver_username))
        receiver = result.scalar_one_or_none()
    if not receiver:
        raise NotFoundError("Trade partner not found")
    return receiver


async def create_offer(db: AsyncSession, sender: User, payload: TradeCreateRequest) -> TradeOfferOut:
    receiver = await _find_receiver(db, payload)
    if receiver.id == sender.id:
        raise ConflictError("You cannot trade with yourself")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot trade")
    if not receiver.accept_trades:
        raise ConflictError("This user is not accepting trade offers")

    if payload.sender_coins > sender.balance:
        raise InsufficientBalanceError("You do not have enough coins for this offer")

    offered_ids = payload.offered_card_ids or []
    requested_ids = payload.requested_card_ids or []
    all_card_ids = list(dict.fromkeys(offered_ids + requested_ids))
    cards_by_id: dict[int, UserCard] = {}
    if all_card_ids:
        # Lock every involved card up front (ascending id order, so a
        # concurrent create_offer touching an overlapping card set can't
        # deadlock) — otherwise two racing offers could both read the same
        # card as unlocked before either commits and both proceed.
        result = await db.execute(
            select(UserCard).where(UserCard.id.in_(all_card_ids)).order_by(UserCard.id)
            .with_for_update().execution_options(populate_existing=True)
        )
        cards_by_id = {c.id: c for c in result.scalars().all()}

    offered_cards: list[UserCard] = []
    if offered_ids:
        unique_offered = list(dict.fromkeys(offered_ids))
        if any(i not in cards_by_id for i in unique_offered):
            raise NotFoundError("One or more offered cards not found")
        offered_cards = [cards_by_id[i] for i in unique_offered]
        for card in offered_cards:
            if card.owner_id != sender.id:
                raise ForbiddenError("You can only offer your own cards")
            if card.is_locked():
                raise ConflictError(f"Card #{card.serial_number} is not available for trade")

    requested_cards: list[UserCard] = []
    if requested_ids:
        unique_requested = list(dict.fromkeys(requested_ids))
        if any(i not in cards_by_id for i in unique_requested):
            raise NotFoundError("One or more requested cards not found")
        requested_cards = [cards_by_id[i] for i in unique_requested]
        for card in requested_cards:
            if card.owner_id != receiver.id:
                raise ConflictError("Requested cards must belong to the trade partner")
            if card.is_locked() or card.hidden_from_trade:
                raise ConflictError(f"Card #{card.serial_number} is not available for trade")

    offer = TradeOffer(
        sender_id=sender.id,
        receiver_id=receiver.id,
        sender_coins=payload.sender_coins,
        receiver_coins=payload.receiver_coins,
        message=payload.message,
        status=TradeStatus.pending,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=TRADE_EXPIRY_HOURS),
    )
    db.add(offer)
    await db.flush()

    for card in offered_cards:
        card.is_locked_in_trade = True
        db.add(card)
        db.add(TradeOfferCard(trade_offer_id=offer.id, user_card_id=card.id, side=TradeCardSide.offered))
    for card in requested_cards:
        card.is_locked_in_trade = True
        db.add(card)
        db.add(TradeOfferCard(trade_offer_id=offer.id, user_card_id=card.id, side=TradeCardSide.requested))

    await notify(
        db, receiver.id, NotificationType.trade_offer_received,
        "Новое предложение обмена", f"{sender.full_display_name()} предложил(а) вам обмен.",
        "trade_offer", offer.id,
    )

    await db.commit()
    await db.refresh(offer)
    return await hydrate_offer(db, offer)


async def _get_offer_or_404(db: AsyncSession, offer_id: int) -> TradeOffer:
    offer = await db.get(TradeOffer, offer_id)
    if not offer:
        raise NotFoundError("Trade offer not found")
    return offer


async def cancel_offer(db: AsyncSession, user: User, offer_id: int) -> TradeOfferOut:
    offer = await _get_offer_or_404(db, offer_id)
    offer = await _expire_if_needed(db, offer)
    if offer.sender_id != user.id:
        raise ForbiddenError("Only the sender can cancel this offer")
    if offer.status != TradeStatus.pending:
        raise ConflictError("This offer is no longer pending")

    offer.status = TradeStatus.cancelled
    offer.resolved_at = datetime.now(timezone.utc)
    await unlock_trade_cards(db, offer.id)
    await notify(
        db, offer.receiver_id, NotificationType.trade_offer_cancelled,
        "Обмен отменён", "Отправитель отменил предложение обмена.", "trade_offer", offer.id,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return await hydrate_offer(db, offer)


async def reject_offer(db: AsyncSession, user: User, offer_id: int) -> TradeOfferOut:
    offer = await _get_offer_or_404(db, offer_id)
    offer = await _expire_if_needed(db, offer)
    if offer.receiver_id != user.id:
        raise ForbiddenError("Only the receiver can reject this offer")
    if offer.status != TradeStatus.pending:
        raise ConflictError("This offer is no longer pending")

    offer.status = TradeStatus.rejected
    offer.resolved_at = datetime.now(timezone.utc)
    await unlock_trade_cards(db, offer.id)
    await notify(
        db, offer.sender_id, NotificationType.trade_offer_rejected,
        "Обмен отклонён", "Получатель отклонил предложение обмена.", "trade_offer", offer.id,
    )
    db.add(offer)
    await db.commit()
    await db.refresh(offer)
    return await hydrate_offer(db, offer)


async def accept_offer(db: AsyncSession, user: User, offer_id: int) -> TradeOfferOut:
    offer = await _get_offer_or_404(db, offer_id)
    offer = await _expire_if_needed(db, offer)
    if offer.receiver_id != user.id:
        raise ForbiddenError("Only the receiver can accept this offer")
    if offer.status != TradeStatus.pending:
        raise ConflictError("This offer is no longer pending")

    trade_cards_result = await db.execute(select(TradeOfferCard).where(TradeOfferCard.trade_offer_id == offer.id))
    trade_cards = trade_cards_result.scalars().all()
    card_ids = sorted({tc.user_card_id for tc in trade_cards})

    first_id, second_id = sorted([offer.sender_id, offer.receiver_id])
    first_user = await lock_user_for_update(db, first_id)
    second_user = await lock_user_for_update(db, second_id)
    sender = first_user if first_user.id == offer.sender_id else second_user
    receiver = first_user if first_user.id == offer.receiver_id else second_user

    # Re-lock the offer and every traded card now that the user locks are
    # held, so a concurrent accept of this same offer (or a second offer
    # racing on one of these cards) can't slip through on stale reads.
    await db.refresh(offer, with_for_update=True)
    if offer.status != TradeStatus.pending:
        raise ConflictError("This offer is no longer pending")

    cards_by_id: dict[int, UserCard] = {}
    if card_ids:
        cards_result = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).order_by(UserCard.id)
            .with_for_update().execution_options(populate_existing=True)
        )
        cards_by_id = {c.id: c for c in cards_result.scalars().all()}

    if len(cards_by_id) != len(card_ids):
        raise ConflictError("One or more traded cards no longer exist")

    for tc in trade_cards:
        card = cards_by_id[tc.user_card_id]
        expected_owner = offer.sender_id if tc.side == TradeCardSide.offered else offer.receiver_id
        if card.owner_id != expected_owner:
            raise ConflictError("Card ownership changed since the offer was created")
        if card.is_locked_by_admin:
            raise ConflictError(f"Card #{card.serial_number} was locked by an administrator")
        if card.is_in_lineup:
            raise ConflictError(f"Card #{card.serial_number} is currently used in a lineup")

    if offer.sender_coins > 0 and sender.balance < offer.sender_coins:
        raise InsufficientBalanceError("Sender no longer has enough coins for this trade")
    if offer.receiver_coins > 0 and receiver.balance < offer.receiver_coins:
        raise InsufficientBalanceError("Receiver no longer has enough coins for this trade")

    for tc in trade_cards:
        card = cards_by_id[tc.user_card_id]
        new_owner_id = offer.receiver_id if tc.side == TradeCardSide.offered else offer.sender_id
        card.owner_id = new_owner_id
        card.is_locked_in_trade = False
        db.add(card)

    if offer.sender_coins > 0:
        await debit_coins(db, sender, offer.sender_coins, TransactionType.trade_coins_sent, "Монеты отправлены при обмене", "trade_offer", offer.id)
        await credit_coins(db, receiver, offer.sender_coins, TransactionType.trade_coins_received, "Монеты получены при обмене", "trade_offer", offer.id)
    if offer.receiver_coins > 0:
        await debit_coins(db, receiver, offer.receiver_coins, TransactionType.trade_coins_sent, "Монеты отправлены при обмене", "trade_offer", offer.id)
        await credit_coins(db, sender, offer.receiver_coins, TransactionType.trade_coins_received, "Монеты получены при обмене", "trade_offer", offer.id)

    offer.status = TradeStatus.accepted
    offer.resolved_at = datetime.now(timezone.utc)
    db.add(offer)

    await notify(
        db, offer.sender_id, NotificationType.trade_offer_accepted,
        "Обмен принят", f"{receiver.full_display_name()} принял(а) ваше предложение обмена.", "trade_offer", offer.id,
    )

    for participant in (sender, receiver):
        completed_count = (
            await db.execute(
                select(func.count(TradeOffer.id)).where(
                    TradeOffer.status == TradeStatus.accepted,
                    or_(TradeOffer.sender_id == participant.id, TradeOffer.receiver_id == participant.id),
                )
            )
        ).scalar_one() + 1  # +1: this offer is committed to `accepted` status below, not yet visible to the count query
        await task_service.evaluate_metric_progress(db, participant, "trades_completed", completed_count)

    await db.commit()
    await db.refresh(offer)
    return await hydrate_offer(db, offer)


async def list_offers(db: AsyncSession, user: User, status: Optional[TradeStatus], direction: Optional[str]) -> list[TradeOfferOut]:
    await expire_stale_trades(db)
    query = select(TradeOffer)
    if direction == "outgoing":
        query = query.where(TradeOffer.sender_id == user.id)
    elif direction == "incoming":
        query = query.where(TradeOffer.receiver_id == user.id)
    else:
        query = query.where(or_(TradeOffer.sender_id == user.id, TradeOffer.receiver_id == user.id))
    if status:
        query = query.where(TradeOffer.status == status)
    query = query.order_by(TradeOffer.created_at.desc())

    offers = (await db.execute(query)).scalars().all()
    return [await hydrate_offer(db, o) for o in offers]


async def get_offer(db: AsyncSession, user: User, offer_id: int) -> TradeOfferOut:
    offer = await _get_offer_or_404(db, offer_id)
    offer = await _expire_if_needed(db, offer)
    if user.id not in (offer.sender_id, offer.receiver_id) and not user.is_admin:
        raise ForbiddenError("You are not part of this trade")
    return await hydrate_offer(db, offer)
