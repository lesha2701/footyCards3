"""«Трансферный рынок»: player-to-player auction of specific card copies.

Money flow (all through wallet_service, every step a CoinTransaction):
  * a bid is debited from the bidder right away (escrow, `auction_bid`);
  * when it is outbid — or an admin removes the lot — it is credited back
    (`auction_refund`);
  * on sale the seller is credited the final price minus the market fee
    (`auction_sale`); the fee is simply never credited anywhere — burnt, an
    inflation sink. «Купить сейчас» debits the buyer the buy-now price
    (`auction_buy_now`) and settles at once.

Only holders of an active «Агентская лицензия» (agent_license_service) may
list lots; anyone not banned may bid and buy. The start price is never below
the copy's card_value (card_value_service), and the card rules are those of
trades: no plain diamonds, valuable copies never from a free source and only
from a «Проверенный аккаунт».

While a lot is active its card is held with `is_locked_in_trade`, the flag
every lineup / squad / trade / quick-sell / upgrade check already honours,
so the copy can't be used, traded or consumed. The card row itself moves to
the buyer (owner_id), so its skill, stars, «Академия» progress, prestige and
serial number go with it.

Concurrency: every mutation takes the row locks in one order — lot → users
(ascending id) → card. Expired lots are closed both lazily on reads and by
the bot's background loop (POST /internal/auction/sweep); the closer takes
the lot with SKIP LOCKED and re-checks status/ends_at under the lock, so a
bid that just extended the lot (anti-sniping), a «купить сейчас» and the two
sweep paths never settle a lot twice. Retried bids are deduplicated by the
unique (bidder_id, idempotency_key) constraint; (lot_id, amount) is unique
too, since bids only go up.
"""
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.auction import AgentLicense, AuctionBid, AuctionLot
from app.models.card import UserCard
from app.models.enums import NotificationType, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.user import User
from app.schemas.auction import (
    AuctionActionOut,
    AuctionBidIn,
    AuctionBidOut,
    AuctionBuyNowIn,
    AuctionInfoOut,
    AuctionLotCreateIn,
    AuctionLotListOut,
    AuctionLotOut,
    AuctionPriceFloorOut,
)
from app.schemas.card import UserCardOut
from app.services.admin_log_service import log_action
from app.services.collection_service import grant_collection_rewards_for_new_cards
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services import agent_license_service
from app.services import card_value_service as cv
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update

ACTIVE = "active"
SOLD = "sold"
EXPIRED = "expired"
CANCELLED = "cancelled"
REMOVED = "removed"

SWEEP_BATCH = 50
LAZY_SWEEP_BATCH = 10
BID_HISTORY_LIMIT = 30
RELATED = "auction_lot"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _name(user: Optional[User]) -> str:
    return user.full_display_name() if user is not None else "Игрок"


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def min_next_bid(lot: AuctionLot, config: GameConfig) -> int:
    """Start price before the first bid, then the current bid plus the bigger
    of the % step and the coin step."""
    if lot.current_bid is None:
        return lot.start_price
    pct_step = -(-lot.current_bid * max(0, config.auction_min_increment_pct) // 100)
    return lot.current_bid + max(1, config.auction_min_increment_coins, pct_step)


def price_floor(card: UserCard, config: GameConfig) -> int:
    """Lowest allowed start price: the copy's card_value (what getting it
    from us costs — card_value_service), never below auction_min_price — so
    a valuable card can't be handed to a second account for pennies.
    «Купить сейчас» must be above the start price, so it is covered too."""
    return max(1, config.auction_min_price, cv.card_value(card, config))


async def listing_block_reason(db: AsyncSession, seller: User, card: UserCard, config: GameConfig) -> Optional[str]:
    """Card rules for listing, the same as for giving a card in a trade
    (trade_guard_service): no plain diamonds; a valuable copy (legendary,
    «Академия», limited) never from a free source and only from a
    «Проверенный аккаунт». The caller has `card.player` loaded."""
    if card.player.rarity == Rarity.diamond and card.player.path_talent_code is None:
        return "Алмазные карточки нельзя продавать на рынке"
    if not cv.is_valuable(card, config):
        return None
    if card.from_free_source:
        return (
            f"«{card.player.display_name}» получена бесплатно (награда, бесплатный пак, колесо…) "
            "и привязана к аккаунту — её нельзя продать на рынке."
        )
    reason = await cv.verified_block_reason(db, seller, config)
    if reason:
        return f"Продавать легендарки, «Академию» и лимитки может только «Проверенный аккаунт». {reason}"
    return None


def fee_for(price: int, fee_pct: int) -> int:
    return price * max(0, fee_pct) // 100


def restriction(user: User, config: GameConfig, now: Optional[datetime] = None) -> Optional[str]:
    """Why this account can't sell or bid right now (None = it can)."""
    now = now or _now()
    if user.is_banned:
        return "Аккаунт заблокирован"
    if user.is_trade_banned:
        return "Тебе временно запрещено торговать"
    days = max(0, config.auction_min_account_age_days)
    if days and user.created_at is not None:
        opens_at = ensure_aware(user.created_at) + timedelta(days=days)
        if opens_at > now:
            left = opens_at - now
            hours = max(1, int(left.total_seconds() // 3600))
            return f"Рынок откроется для тебя через {hours} ч — торговать можно с {days}-го дня в игре"
    return None


def _require_enabled(config: GameConfig) -> None:
    if not config.auction_enabled:
        raise ConflictError("Трансферный рынок сейчас закрыт")


def _require_can_trade(user: User, config: GameConfig) -> None:
    reason = restriction(user, config)
    if reason:
        raise ForbiddenError(reason)


def _is_open(lot: AuctionLot, now: datetime) -> bool:
    return lot.status == ACTIVE and ensure_aware(lot.ends_at) > now


# ---------------------------------------------------------------------------
# Locks (always lot → users by id → card)
# ---------------------------------------------------------------------------

async def _lock_lot(db: AsyncSession, lot_id: int, skip_locked: bool = False) -> Optional[AuctionLot]:
    result = await db.execute(
        select(AuctionLot).where(AuctionLot.id == lot_id)
        .with_for_update(skip_locked=skip_locked).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _lock_users(db: AsyncSession, user_ids: Iterable[Optional[int]]) -> dict[int, User]:
    return {uid: await lock_user_for_update(db, uid) for uid in sorted({u for u in user_ids if u is not None})}


async def _lock_card(db: AsyncSession, card_id: int) -> Optional[UserCard]:
    result = await db.execute(
        select(UserCard).where(UserCard.id == card_id)
        .options(selectinload(UserCard.player))
        .with_for_update(of=UserCard).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _card_with_player(db: AsyncSession, card_id: int) -> Optional[UserCard]:
    """Unlocked read with the player loaded even when the card is already in
    the session's identity map (db.get would skip the loader option)."""
    result = await db.execute(
        select(UserCard).where(UserCard.id == card_id)
        .options(selectinload(UserCard.player)).execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def _leading_bid(db: AsyncSession, lot_id: int) -> Optional[AuctionBid]:
    return (
        await db.execute(
            select(AuctionBid).where(AuctionBid.lot_id == lot_id, AuctionBid.status == "leading")
            .order_by(AuctionBid.amount.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def _check_win_limit(db: AsyncSession, buyer_id: int, lot: AuctionLot, config: GameConfig) -> None:
    """One buyer may win at most N lots of one seller per 24 h — counting the
    lots of that seller they're leading right now, since each could still be
    won. Caps coin laundering between two accounts of the same person."""
    limit = config.auction_max_wins_per_seller_daily
    if limit <= 0:
        return
    since = _now() - timedelta(hours=24)
    count = (
        await db.execute(
            select(func.count(AuctionLot.id)).where(
                AuctionLot.seller_id == lot.seller_id,
                AuctionLot.id != lot.id,
                or_(
                    and_(AuctionLot.status == SOLD, AuctionLot.winner_id == buyer_id, AuctionLot.closed_at >= since),
                    and_(AuctionLot.status == ACTIVE, AuctionLot.current_bidder_id == buyer_id),
                ),
            )
        )
    ).scalar_one()
    if count >= limit:
        raise ConflictError(f"У одного продавца можно выиграть не больше {limit} лотов за сутки")


async def _refund_leader(
    db: AsyncSession, lot: AuctionLot, users: dict[int, User], card_name: str, new_status: str, notify_leader: bool,
) -> None:
    """Returns the leading bid's escrow to its bidder (the caller holds their lock)."""
    if lot.current_bidder_id is None or lot.current_bid is None:
        return
    leader = users[lot.current_bidder_id]
    await credit_coins(
        db, leader, lot.current_bid, TransactionType.auction_refund,
        f"Возврат ставки на рынке: {card_name}", RELATED, lot.id,
    )
    bid = await _leading_bid(db, lot.id)
    if bid is not None:
        bid.status = new_status
    if notify_leader:
        await notify(
            db, leader.id, NotificationType.auction_outbid, "Вашу ставку перебили",
            f"{card_name}: ставку {lot.current_bid} перебили, монеты вернулись на баланс.", RELATED, lot.id,
        )


async def _settle_sale(
    db: AsyncSession, lot: AuctionLot, card: UserCard, seller: User, buyer: User, price: int, reason: str,
) -> None:
    """Moves the card row to the buyer and pays the seller price − fee. The
    buyer's coins were already taken (escrowed bid or buy-now debit)."""
    now = _now()
    fee = fee_for(price, lot.fee_pct)
    card.owner_id = buyer.id
    card.is_locked_in_trade = False
    lot.status = SOLD
    lot.winner_id = buyer.id
    lot.final_price = price
    lot.fee_amount = fee
    lot.closed_at = now
    lot.close_reason = reason
    lot.current_bid = price
    lot.current_bidder_id = buyer.id
    name = card.player.display_name
    await credit_coins(
        db, seller, price - fee, TransactionType.auction_sale,
        f"Продажа на рынке: {name} за {price} (комиссия {fee})", RELATED, lot.id,
    )
    await grant_collection_rewards_for_new_cards(db, buyer, [card.player_id])
    await notify(
        db, seller.id, NotificationType.auction_sold, "Лот продан",
        f"{name} продан за {price}. Комиссия рынка {fee}, вам начислено {price - fee}.", RELATED, lot.id,
    )
    await notify(
        db, buyer.id, NotificationType.auction_won, "Вы выиграли лот",
        f"{name} теперь в вашей коллекции (цена {price}).", RELATED, lot.id,
    )


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------

async def _hydrate(
    db: AsyncSession, lots: list[AuctionLot], viewer_id: int, config: GameConfig, with_bids: bool = False,
) -> list[AuctionLotOut]:
    if not lots:
        return []
    card_ids = {lot.user_card_id for lot in lots}
    cards = {
        c.id: c for c in (
            await db.execute(
                select(UserCard).where(UserCard.id.in_(card_ids)).options(selectinload(UserCard.player))
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
    }
    user_ids = {lot.seller_id for lot in lots} | {lot.current_bidder_id for lot in lots if lot.current_bidder_id}
    lot_ids = [lot.id for lot in lots]
    my_max = dict(
        (
            await db.execute(
                select(AuctionBid.lot_id, func.max(AuctionBid.amount))
                .where(AuctionBid.lot_id.in_(lot_ids), AuctionBid.bidder_id == viewer_id)
                .group_by(AuctionBid.lot_id)
            )
        ).all()
    )
    bids_by_lot: dict[int, list[AuctionBid]] = {}
    if with_bids:
        bid_rows = (
            await db.execute(
                select(AuctionBid).where(AuctionBid.lot_id.in_(lot_ids))
                .order_by(AuctionBid.amount.desc()).limit(BID_HISTORY_LIMIT * len(lot_ids))
            )
        ).scalars().all()
        for bid in bid_rows:
            bids_by_lot.setdefault(bid.lot_id, []).append(bid)
            user_ids.add(bid.bidder_id)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()}
    now = _now()
    seller_ids = {lot.seller_id for lot in lots}
    agents = {
        lic.user_id for lic in (
            await db.execute(select(AgentLicense).where(AgentLicense.user_id.in_(seller_ids)))
        ).scalars().all()
        if agent_license_service.is_active(lic, now)
    }

    out = []
    for lot in lots:
        card = cards.get(lot.user_card_id)
        if card is None:
            continue
        bids = None
        if with_bids:
            bids = [
                AuctionBidOut(
                    id=b.id, bidder_name=_name(users.get(b.bidder_id)), is_mine=b.bidder_id == viewer_id,
                    amount=b.amount, kind=b.kind, status=b.status, created_at=ensure_aware(b.created_at),
                )
                for b in bids_by_lot.get(lot.id, [])[:BID_HISTORY_LIMIT]
            ]
        out.append(AuctionLotOut(
            id=lot.id,
            card=UserCardOut.model_validate(card),
            seller_id=lot.seller_id,
            seller_name=_name(users.get(lot.seller_id)),
            seller_is_agent=lot.seller_id in agents,
            status=lot.status,
            start_price=lot.start_price,
            buy_now_price=lot.buy_now_price,
            current_bid=lot.current_bid,
            bid_count=lot.bid_count,
            min_next_bid=min_next_bid(lot, config),
            fee_pct=lot.fee_pct,
            duration_hours=lot.duration_hours,
            ends_at=ensure_aware(lot.ends_at),
            created_at=ensure_aware(lot.created_at),
            closed_at=ensure_aware(lot.closed_at) if lot.closed_at else None,
            final_price=lot.final_price,
            fee_amount=lot.fee_amount,
            close_reason=lot.close_reason if lot.status == REMOVED else None,
            is_mine=lot.seller_id == viewer_id,
            i_am_leading=lot.status == ACTIVE and lot.current_bidder_id == viewer_id,
            i_won=lot.status == SOLD and lot.winner_id == viewer_id,
            my_max_bid=my_max.get(lot.id),
            leader_name=_name(users.get(lot.current_bidder_id)) if lot.current_bidder_id else None,
            server_now=now,
            bids=bids,
        ))
    return out


async def _one(db: AsyncSession, lot: AuctionLot, viewer_id: int, config: GameConfig, with_bids: bool = True) -> AuctionLotOut:
    return (await _hydrate(db, [lot], viewer_id, config, with_bids=with_bids))[0]


# ---------------------------------------------------------------------------
# Closing expired lots (lazy on reads + bot loop)
# ---------------------------------------------------------------------------

async def close_if_due(db: AsyncSession, lot_id: int) -> bool:
    """Settles one expired lot. Takes it with SKIP LOCKED (a bid / buy-now /
    the other sweep path holding it → leave it to them) and re-checks
    status/ends_at under the lock (a last-minute bid may have extended it)."""
    lot = await _lock_lot(db, lot_id, skip_locked=True)
    now = _now()
    if lot is None or lot.status != ACTIVE or ensure_aware(lot.ends_at) > now:
        # Nothing changed — commit (not rollback, which would expire the
        # request's already-loaded objects) just to release the lock.
        await db.commit()
        return False

    users = await _lock_users(db, [lot.seller_id, lot.current_bidder_id])
    card = await _lock_card(db, lot.user_card_id)
    if card is None:  # card rows are never deleted while locked; defensive
        await _refund_leader(db, lot, users, "лот", "refunded", notify_leader=False)
        lot.status, lot.closed_at, lot.close_reason = REMOVED, now, "Карточка недоступна"
        await db.commit()
        return True
    name = card.player.display_name

    if card.is_locked_by_admin:
        # An admin froze this copy mid-auction: nobody gets it, money goes back.
        await _refund_leader(db, lot, users, name, "refunded", notify_leader=False)
        card.is_locked_in_trade = False
        lot.status, lot.closed_at, lot.close_reason = REMOVED, now, "Карточка заблокирована администратором"
    elif lot.current_bidder_id is not None and lot.current_bid is not None:
        bid = await _leading_bid(db, lot.id)
        if bid is not None:
            bid.status = "won"
        await _settle_sale(
            db, lot, card, users[lot.seller_id], users[lot.current_bidder_id], lot.current_bid, "auction",
        )
    else:
        card.is_locked_in_trade = False
        lot.status, lot.closed_at = EXPIRED, now
        await notify(
            db, lot.seller_id, NotificationType.auction_expired, "Лот не продан",
            f"{name}: ставок не было, карточка вернулась в коллекцию.", RELATED, lot.id,
        )
    await db.commit()
    return True


async def sweep_due(db: AsyncSession, limit: int = SWEEP_BATCH) -> int:
    """Background tick (bot → POST /internal/auction/sweep) and the lazy
    sweep on reads: closes every lot whose time ran out."""
    ids = (
        await db.execute(
            select(AuctionLot.id).where(AuctionLot.status == ACTIVE, AuctionLot.ends_at <= _now())
            .order_by(AuctionLot.ends_at).limit(limit)
        )
    ).scalars().all()
    closed = 0
    for lot_id in list(ids):
        if await close_if_due(db, lot_id):
            closed += 1
    return closed


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

async def get_info(db: AsyncSession, user: User) -> AuctionInfoOut:
    config = await get_config(db)
    active = (
        await db.execute(
            select(func.count(AuctionLot.id)).where(AuctionLot.seller_id == user.id, AuctionLot.status == ACTIVE)
        )
    ).scalar_one()
    return AuctionInfoOut(
        enabled=config.auction_enabled,
        durations_hours=[int(h) for h in (config.auction_durations_hours or [])],
        fee_pct=config.auction_fee_pct,
        min_increment_pct=config.auction_min_increment_pct,
        min_increment_coins=config.auction_min_increment_coins,
        min_price=config.auction_min_price,
        max_active_lots=config.auction_max_active_lots,
        snipe_window_seconds=config.auction_snipe_window_seconds,
        snipe_extend_seconds=config.auction_snipe_extend_seconds,
        min_account_age_days=config.auction_min_account_age_days,
        my_active_lots=active,
        restriction=restriction(user, config),
        license=await agent_license_service.status(db, user, config),
        server_now=_now(),
    )


async def price_floor_for(db: AsyncSession, user: User, user_card_id: int) -> AuctionPriceFloorOut:
    """The start-price floor for one of the viewer's copies, for the listing form."""
    card = await _card_with_player(db, user_card_id)
    if card is None or card.owner_id != user.id:
        raise NotFoundError("Карточка не найдена")
    config = await get_config(db)
    return AuctionPriceFloorOut(
        user_card_id=card.id, min_price=price_floor(card, config), valuable=cv.is_valuable(card, config),
        block_reason=await listing_block_reason(db, user, card, config),
    )


async def list_lots(
    db: AsyncSession,
    user: User,
    *,
    search: Optional[str] = None,
    rarity: Optional[Rarity] = None,
    position: Optional[str] = None,
    skill: Optional[str] = None,
    min_stars: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: str = "ending",
    limit: int = 30,
    offset: int = 0,
) -> AuctionLotListOut:
    await sweep_due(db, LAZY_SWEEP_BATCH)
    config = await get_config(db)
    price = func.coalesce(AuctionLot.current_bid, AuctionLot.start_price)
    query = (
        select(AuctionLot)
        .join(UserCard, UserCard.id == AuctionLot.user_card_id)
        .join(Player, Player.id == AuctionLot.player_id)
        .where(AuctionLot.status == ACTIVE, AuctionLot.ends_at > _now())
    )
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(
            Player.display_name.ilike(pattern), Player.last_name.ilike(pattern), Player.first_name.ilike(pattern),
        ))
    if rarity is not None:
        query = query.where(Player.rarity == rarity)
    if position:
        query = query.where(Player.position == position)
    if skill == "any":
        query = query.where(UserCard.skill_code.is_not(None))
    elif skill:
        query = query.where(UserCard.skill_code == skill)
    if min_stars:
        query = query.where(UserCard.stars >= min_stars)
    if min_price is not None:
        query = query.where(price >= min_price)
    if max_price is not None:
        query = query.where(price <= max_price)

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    order = {
        "ending": [AuctionLot.ends_at.asc()],
        "newest": [AuctionLot.created_at.desc()],
        "price_asc": [price.asc()],
        "price_desc": [price.desc()],
    }.get(sort, [AuctionLot.ends_at.asc()])
    lots = (await db.execute(query.order_by(*order, AuctionLot.id).limit(limit).offset(offset))).scalars().all()
    return AuctionLotListOut(items=await _hydrate(db, list(lots), user.id, config), total=total)


async def my_lots(db: AsyncSession, user: User) -> list[AuctionLotOut]:
    await sweep_due(db, LAZY_SWEEP_BATCH)
    config = await get_config(db)
    lots = (
        await db.execute(
            select(AuctionLot).where(AuctionLot.seller_id == user.id)
            .order_by((AuctionLot.status == ACTIVE).desc(), AuctionLot.created_at.desc()).limit(50)
        )
    ).scalars().all()
    return await _hydrate(db, list(lots), user.id, config)


async def my_bids(db: AsyncSession, user: User) -> list[AuctionLotOut]:
    await sweep_due(db, LAZY_SWEEP_BATCH)
    config = await get_config(db)
    bid_lots = select(AuctionBid.lot_id).where(AuctionBid.bidder_id == user.id)
    lots = (
        await db.execute(
            select(AuctionLot).where(AuctionLot.id.in_(bid_lots))
            .order_by((AuctionLot.status == ACTIVE).desc(), AuctionLot.ends_at.desc()).limit(50)
        )
    ).scalars().all()
    return await _hydrate(db, list(lots), user.id, config)


async def get_lot(db: AsyncSession, user: User, lot_id: int) -> AuctionLotOut:
    lot = await db.get(AuctionLot, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")
    if lot.status == ACTIVE and ensure_aware(lot.ends_at) <= _now():
        await close_if_due(db, lot_id)
    lot = (
        await db.execute(select(AuctionLot).where(AuctionLot.id == lot_id).execution_options(populate_existing=True))
    ).scalar_one()
    return await _one(db, lot, user.id, await get_config(db))


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

async def create_lot(db: AsyncSession, user: User, payload: AuctionLotCreateIn) -> AuctionLotOut:
    config = await get_config(db)
    _require_enabled(config)
    seller = await lock_user_for_update(db, user.id)
    _require_can_trade(seller, config)
    if not await agent_license_service.has_active(db, seller.id):
        raise ForbiddenError(
            "Выставлять на рынок могут только агенты — купи «Агентскую лицензию» в разделе «Рынок». "
            "Ставить и покупать можно и без неё.",
            details={"rule": "agent_license_required"},
        )
    durations = [int(h) for h in (config.auction_durations_hours or [])]
    if payload.duration_hours not in durations:
        raise ConflictError("Недопустимый срок лота", details={"allowed": durations})

    card = await _lock_card(db, payload.user_card_id)
    if card is None:
        raise NotFoundError("Карточка не найдена")
    if card.owner_id != seller.id:
        raise ForbiddenError("Это не твоя карточка")

    # Replay of a create that already went through (double tap / retry).
    existing = (
        await db.execute(
            select(AuctionLot).where(AuctionLot.user_card_id == card.id, AuctionLot.status == ACTIVE)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.seller_id == seller.id:
            return await _one(db, existing, seller.id, config)
        raise ConflictError("Карточка уже выставлена на рынок")

    reason = await listing_block_reason(db, seller, card, config)
    if reason:
        raise ConflictError(reason, details={"rule": "auction_card_not_listable"})
    if card.is_locked_by_admin:
        raise ConflictError("Карточка заблокирована администратором")
    if card.is_locked_in_trade:
        raise ConflictError("Карточка участвует в обмене")
    if card.is_in_lineup or card.is_in_tactico_squad:
        raise ConflictError("Карточка стоит в составе — сначала убери её оттуда")

    active = (
        await db.execute(
            select(func.count(AuctionLot.id)).where(AuctionLot.seller_id == seller.id, AuctionLot.status == ACTIVE)
        )
    ).scalar_one()
    if active >= config.auction_max_active_lots:
        raise ConflictError(f"Можно держать не больше {config.auction_max_active_lots} активных лотов")

    floor = price_floor(card, config)
    if payload.start_price < floor:
        raise ConflictError(f"Стартовая цена не может быть ниже {floor}", details={"min_price": floor})
    if payload.buy_now_price is not None and payload.buy_now_price <= payload.start_price:
        raise ConflictError("Цена «Купить сейчас» должна быть выше стартовой")

    copies = (
        await db.execute(
            select(func.count(UserCard.id)).where(UserCard.owner_id == seller.id, UserCard.player_id == card.player_id)
        )
    ).scalar_one()
    if copies <= 1 and not payload.confirm_last_copy:
        raise ConflictError(
            "Это твоя последняя копия этого игрока — подтверди выставление",
            details={"requires_confirmation": True},
        )

    lot = AuctionLot(
        seller_id=seller.id,
        user_card_id=card.id,
        player_id=card.player_id,
        status=ACTIVE,
        start_price=payload.start_price,
        buy_now_price=payload.buy_now_price,
        bid_count=0,
        fee_pct=config.auction_fee_pct,
        duration_hours=payload.duration_hours,
        ends_at=_now() + timedelta(hours=payload.duration_hours),
    )
    card.is_locked_in_trade = True
    db.add(lot)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Карточка уже выставлена на рынок")
    await db.refresh(lot)
    return await _one(db, lot, seller.id, config)


async def _replay(db: AsyncSession, user: User, lot: AuctionLot, config: GameConfig) -> AuctionActionOut:
    await db.commit()  # release the lot lock
    fresh = await db.get(User, user.id)
    await db.refresh(fresh)
    return AuctionActionOut(lot=await _one(db, lot, user.id, config), new_balance=fresh.balance)


async def place_bid(db: AsyncSession, user: User, lot_id: int, payload: AuctionBidIn) -> AuctionActionOut:
    config = await get_config(db)
    _require_enabled(config)
    lot = await _lock_lot(db, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")

    replay = (
        await db.execute(
            select(AuctionBid).where(AuctionBid.bidder_id == user.id, AuctionBid.idempotency_key == payload.idempotency_key)
        )
    ).scalar_one_or_none()
    if replay is not None:
        if replay.lot_id != lot.id:
            raise ConflictError("Повторный ключ ставки")
        return await _replay(db, user, lot, config)

    now = _now()
    if not _is_open(lot, now):
        raise ConflictError("Торги по этому лоту закончились")
    if lot.seller_id == user.id:
        raise ForbiddenError("Нельзя делать ставку на свой лот")
    if lot.current_bidder_id == user.id:
        raise ConflictError("Твоя ставка и так лидирует")
    need = min_next_bid(lot, config)
    if payload.amount < need:
        raise ConflictError(f"Минимальная ставка сейчас — {need}", details={"min_next_bid": need})
    if lot.buy_now_price is not None and payload.amount >= lot.buy_now_price:
        raise ConflictError(
            "Ставка не меньше цены «Купить сейчас» — просто купи лот",
            details={"buy_now_price": lot.buy_now_price},
        )

    users = await _lock_users(db, [user.id, lot.current_bidder_id])
    bidder = users[user.id]
    _require_can_trade(bidder, config)
    await _check_win_limit(db, bidder.id, lot, config)

    card = await _card_with_player(db, lot.user_card_id)
    name = card.player.display_name if card is not None else "лот"
    await debit_coins(db, bidder, payload.amount, TransactionType.auction_bid, f"Ставка на рынке: {name}", RELATED, lot.id)
    await _refund_leader(db, lot, users, name, "outbid", notify_leader=True)

    db.add(AuctionBid(
        lot_id=lot.id, bidder_id=bidder.id, amount=payload.amount, kind="bid", status="leading",
        idempotency_key=payload.idempotency_key,
    ))
    lot.current_bid = payload.amount
    lot.current_bidder_id = bidder.id
    lot.bid_count += 1
    window = timedelta(seconds=max(0, config.auction_snipe_window_seconds))
    if window and ensure_aware(lot.ends_at) - now < window:
        lot.ends_at = now + timedelta(seconds=max(0, config.auction_snipe_extend_seconds))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Ставка уже принята — обнови лот")
    await db.refresh(bidder)
    return AuctionActionOut(lot=await _one(db, lot, bidder.id, config), new_balance=bidder.balance)


async def buy_now(db: AsyncSession, user: User, lot_id: int, payload: AuctionBuyNowIn) -> AuctionActionOut:
    config = await get_config(db)
    _require_enabled(config)
    lot = await _lock_lot(db, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")
    if lot.status == SOLD and lot.winner_id == user.id and lot.close_reason == "buy_now":
        return await _replay(db, user, lot, config)

    now = _now()
    if not _is_open(lot, now):
        raise ConflictError("Торги по этому лоту закончились")
    if lot.seller_id == user.id:
        raise ForbiddenError("Нельзя купить свой лот")
    if lot.buy_now_price is None:
        raise ConflictError("У этого лота нет цены «Купить сейчас»")
    if payload.expected_price != lot.buy_now_price:
        raise ConflictError("Цена лота изменилась — обнови страницу")

    users = await _lock_users(db, [user.id, lot.seller_id, lot.current_bidder_id])
    buyer, seller = users[user.id], users[lot.seller_id]
    _require_can_trade(buyer, config)
    await _check_win_limit(db, buyer.id, lot, config)
    card = await _lock_card(db, lot.user_card_id)
    if card is None or card.owner_id != seller.id:
        raise ConflictError("Карточка недоступна")
    if card.is_locked_by_admin:
        raise ConflictError("Карточка заблокирована администратором")
    name = card.player.display_name

    price = lot.buy_now_price
    # Refund the current leader first (it may be the buyer themself).
    await _refund_leader(db, lot, users, name, "outbid", notify_leader=lot.current_bidder_id != buyer.id)
    await debit_coins(db, buyer, price, TransactionType.auction_buy_now, f"Покупка на рынке: {name}", RELATED, lot.id)
    db.add(AuctionBid(lot_id=lot.id, bidder_id=buyer.id, amount=price, kind="buy_now", status="won"))
    lot.bid_count += 1
    await _settle_sale(db, lot, card, seller, buyer, price, "buy_now")
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("Лот уже куплен")
    await db.refresh(buyer)
    return AuctionActionOut(lot=await _one(db, lot, buyer.id, config), new_balance=buyer.balance)


async def cancel_lot(db: AsyncSession, user: User, lot_id: int) -> AuctionLotOut:
    """Seller takes the lot back — only while nobody has bid. Works even with
    the market switched off, so cards are never stuck."""
    config = await get_config(db)
    lot = await _lock_lot(db, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")
    if lot.seller_id != user.id:
        raise ForbiddenError("Это не твой лот")
    if lot.status != ACTIVE:
        raise ConflictError("Лот уже закрыт")
    if lot.current_bidder_id is not None or lot.bid_count > 0:
        raise ConflictError("Лот со ставками снять нельзя")
    card = await _lock_card(db, lot.user_card_id)
    if card is not None:
        card.is_locked_in_trade = False
    lot.status, lot.closed_at = CANCELLED, _now()
    await db.commit()
    return await _one(db, lot, user.id, config)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def admin_list(
    db: AsyncSession, status: Optional[str] = None, username: Optional[str] = None, limit: int = 200,
) -> list[AuctionLotOut]:
    config = await get_config(db)
    query = select(AuctionLot).order_by(AuctionLot.created_at.desc()).limit(limit)
    if status:
        query = query.where(AuctionLot.status == status)
    if username:
        ids = (await db.execute(select(User.id).where(User.username.ilike(f"%{username}%")))).scalars().all()
        if not ids:
            return []
        query = query.where(or_(
            AuctionLot.seller_id.in_(ids), AuctionLot.current_bidder_id.in_(ids), AuctionLot.winner_id.in_(ids),
        ))
    lots = (await db.execute(query)).scalars().all()
    return await _hydrate(db, list(lots), 0, config)


async def admin_get(db: AsyncSession, lot_id: int) -> AuctionLotOut:
    lot = await db.get(AuctionLot, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")
    return await _one(db, lot, 0, await get_config(db))


async def admin_remove(
    db: AsyncSession, admin: User, lot_id: int, reason: str, ip_address: Optional[str] = None,
) -> AuctionLotOut:
    """Takes an active lot off the market: the leading bid is refunded, the
    card goes back to the seller unlocked, both are notified, and the action
    is written to the admin log."""
    config = await get_config(db)
    lot = await _lock_lot(db, lot_id)
    if lot is None:
        raise NotFoundError("Лот не найден")
    if lot.status != ACTIVE:
        raise ConflictError("Снять можно только активный лот")
    bidder_id, bid = lot.current_bidder_id, lot.current_bid
    users = await _lock_users(db, [lot.seller_id, lot.current_bidder_id])
    card = await _lock_card(db, lot.user_card_id)
    name = card.player.display_name if card is not None else "лот"
    await _refund_leader(db, lot, users, name, "refunded", notify_leader=False)
    if card is not None:
        card.is_locked_in_trade = False
    lot.status, lot.closed_at, lot.close_reason = REMOVED, _now(), reason
    body = f"{name}: лот снят администрацией. Причина: {reason}"
    await notify(db, lot.seller_id, NotificationType.auction_removed, "Лот снят с рынка", body, RELATED, lot.id)
    if bidder_id is not None:
        await notify(
            db, bidder_id, NotificationType.auction_removed, "Лот снят с рынка",
            f"{body}. Ставка {bid} возвращена.", RELATED, lot.id,
        )
    await log_action(
        db, admin.id, "auction_remove_lot", "auction_lot", lot.id,
        old_value={"status": ACTIVE, "current_bid": bid, "current_bidder_id": bidder_id},
        new_value={"status": REMOVED}, ip_address=ip_address, extra=reason,
    )
    await db.commit()
    return await _one(db, lot, 0, config)
