"""«Паспорт карты»: the story of one copy.

Its owners come from the two ways a copy changes hands: an accepted trade
(an «offered» card goes sender → receiver, a «requested» one receiver →
sender) and a sold market lot (seller → winner). The first owner is the one
the earliest move took it from, or the current owner when it never moved.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import NotFoundError
from app.models.auction import AuctionLot
from app.models.card import UserCard
from app.models.enums import TradeCardSide, TradeStatus
from app.models.trade import TradeOffer, TradeOfferCard
from app.models.user import User
from app.schemas.collection import CardPassportOut, CardPassportOwnerOut

MAX_OWNERS_SHOWN = 12


async def card_passport(db: AsyncSession, user: User, card_id: int) -> CardPassportOut:
    card = (
        await db.execute(select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player)))
    ).scalar_one_or_none()
    if card is None or card.owner_id != user.id:
        raise NotFoundError("Card not found")

    # (when, from, to, via) for every move of this copy.
    moves: list[tuple] = []
    trade_rows = await db.execute(
        select(TradeOffer.resolved_at, TradeOffer.created_at, TradeOffer.sender_id, TradeOffer.receiver_id, TradeOfferCard.side)
        .join(TradeOfferCard, TradeOfferCard.trade_offer_id == TradeOffer.id)
        .where(TradeOfferCard.user_card_id == card.id, TradeOffer.status == TradeStatus.accepted)
    )
    for resolved_at, created_at, sender_id, receiver_id, side in trade_rows:
        src, dst = (sender_id, receiver_id) if side == TradeCardSide.offered else (receiver_id, sender_id)
        moves.append((resolved_at or created_at, src, dst, "trade"))
    lot_rows = await db.execute(
        select(AuctionLot.closed_at, AuctionLot.ends_at, AuctionLot.seller_id, AuctionLot.winner_id).where(
            AuctionLot.user_card_id == card.id, AuctionLot.status == "sold", AuctionLot.winner_id.is_not(None)
        )
    )
    for closed_at, ends_at, seller_id, winner_id in lot_rows:
        moves.append((closed_at or ends_at, seller_id, winner_id, "market"))
    moves.sort(key=lambda m: m[0])

    chain: list[tuple[int, str | None, object]] = [(moves[0][1] if moves else card.owner_id, None, None)]
    for at, _src, dst, via in moves:
        if dst != chain[-1][0]:
            chain.append((dst, via, at))
    if chain[-1][0] != card.owner_id:  # history gap (e.g. an admin move): end on the real owner
        chain.append((card.owner_id, None, None))
    chain = chain[-MAX_OWNERS_SHOWN:]

    number_one = (
        await db.execute(
            select(UserCard.owner_id).where(UserCard.player_id == card.player_id, UserCard.serial_number == 1)
        )
    ).scalar_one_or_none()

    ids = {owner for owner, _, _ in chain} | ({number_one} if number_one else set())
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()}

    def name(uid: int) -> str:
        u = users.get(uid)
        return u.full_display_name() if u else "Игрок"

    return CardPassportOut(
        card_id=card.id,
        serial_number=card.serial_number,
        printed=max(card.player.next_serial_number - 1, card.serial_number),
        edition_size=card.player.edition_size,
        acquired_at=card.acquired_at,
        source=card.source,
        owners=[CardPassportOwnerOut(name=name(uid), is_you=uid == user.id, via=via, at=at) for uid, via, at in chain],
        arena_goals=card.arena_goals or 0,
        arena_assists=card.arena_assists or 0,
        arena_mvps=card.arena_mvps or 0,
        number_one_owner=name(number_one) if number_one else None,
        number_one_is_you=number_one == user.id,
    )
