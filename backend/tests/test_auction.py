"""«Трансферный рынок» (services/auction_service.py) — rules, escrow and
settlement on the SQLite test DB. Row locks / SKIP LOCKED races are in
test_auction_postgres.py (real PostgreSQL)."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError, ConflictError, ForbiddenError
from app.models.auction import AuctionBid, AuctionLot
from app.models.card import UserCard
from app.models.enums import CardSource, NotificationType, Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.notification import Notification
from app.models.player import Player
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.schemas.auction import AuctionBidIn, AuctionBuyNowIn, AuctionLotCreateIn
from app.schemas.trade import TradeCreateRequest
from app.services import auction_service, collection_service, trade_service

OLD = datetime.now(timezone.utc) - timedelta(days=30)


@pytest.fixture
async def config(db_session):
    cfg = GameConfig(id=1, auction_enabled=True)
    db_session.add(cfg)
    await db_session.commit()
    return cfg


async def _user(db, balance=10_000, created_at=OLD, name="U") -> User:
    user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name=name, balance=balance, created_at=created_at)
    db.add(user)
    await db.commit()
    return user


async def _card(db, owner: User, copies=2, quick_sell=20, rarity=Rarity.rare, rating=80, **card_fields) -> UserCard:
    tag = uuid.uuid4().hex[:6]
    player = Player(
        first_name="A", last_name=tag, display_name=f"Игрок {tag}", rating=rating, rarity=rarity, country="X",
        club="Y", position=Position.ST, quick_sell_price=quick_sell, is_active=True,
    )
    db.add(player)
    await db.flush()
    cards = [
        UserCard(owner_id=owner.id, player_id=player.id, source=CardSource.seed, serial_number=i + 1, **card_fields)
        for i in range(copies)
    ]
    db.add_all(cards)
    await db.commit()
    return cards[0]


def _key() -> str:
    return uuid.uuid4().hex


async def _list(db, seller, card, start=100, buy_now=None, hours=6, **kw):
    return await auction_service.create_lot(
        db, seller, AuctionLotCreateIn(user_card_id=card.id, start_price=start, buy_now_price=buy_now, duration_hours=hours, **kw),
    )


async def _bid(db, user, lot_id, amount, key=None):
    return await auction_service.place_bid(db, user, lot_id, AuctionBidIn(amount=amount, idempotency_key=key or _key()))


async def _expire(db, lot_id):
    lot = await db.get(AuctionLot, lot_id)
    lot.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()


async def _balance(db, user_id) -> int:
    return (await db.execute(select(User.balance).where(User.id == user_id))).scalar_one()


async def test_create_lot_locks_card_and_validates(db_session, config):
    seller = await _user(db_session)
    card = await _card(db_session, seller, quick_sell=50)

    with pytest.raises(ConflictError):  # below the quick-sell floor
        await _list(db_session, seller, card, start=49)
    with pytest.raises(ConflictError):  # not an allowed duration
        await _list(db_session, seller, card, start=60, hours=2)
    with pytest.raises(ConflictError):  # buy-now must exceed start
        await _list(db_session, seller, card, start=60, buy_now=60)

    lot = await _list(db_session, seller, card, start=60, buy_now=200)
    assert lot.status == "active" and lot.min_next_bid == 60 and lot.fee_pct == 10
    await db_session.refresh(card)
    assert card.is_locked_in_trade

    # A replayed create returns the same lot instead of a second one.
    again = await _list(db_session, seller, card, start=60, buy_now=200)
    assert again.id == lot.id
    count = (await db_session.execute(select(func.count(AuctionLot.id)))).scalar_one()
    assert count == 1


async def test_last_copy_needs_confirmation_and_diamond_is_refused(db_session, config):
    seller = await _user(db_session)
    single = await _card(db_session, seller, copies=1)
    with pytest.raises(ConflictError) as exc:
        await _list(db_session, seller, single)
    assert exc.value.details.get("requires_confirmation")
    await _list(db_session, seller, single, confirm_last_copy=True)

    diamond = await _card(db_session, seller, rarity=Rarity.diamond)
    with pytest.raises(ConflictError):
        await _list(db_session, seller, diamond)


async def test_premium_cards_start_at_premium_floor(db_session, config):
    seller = await _user(db_session)
    top = await _card(db_session, seller, rating=95)
    with pytest.raises(ConflictError) as exc:
        await _list(db_session, seller, top, start=49_999)
    assert exc.value.details["min_price"] == 50_000
    await _list(db_session, seller, top, start=50_000, buy_now=60_000)

    # 94 + one earned star = 95 → premium too; a plain 94 is not.
    boosted = await _card(db_session, seller, rating=94, stars=1, star_rating_bonus=1)
    with pytest.raises(ConflictError):
        await _list(db_session, seller, boosted, start=1000)
    plain = await _card(db_session, seller, rating=94)
    await _list(db_session, seller, plain, start=1000)
    assert (await auction_service.price_floor_for(db_session, seller, top.id)).min_price == 50_000


async def test_listed_card_is_blocked_everywhere_else(db_session, config):
    seller = await _user(db_session)
    other = await _user(db_session)
    card = await _card(db_session, seller)
    await _list(db_session, seller, card)

    with pytest.raises(AppError):
        await collection_service.sell_cards(db_session, seller, [card.id], confirm_last_copy=True)
    with pytest.raises(AppError):
        await trade_service.create_offer(
            db_session, seller, TradeCreateRequest(receiver_id=other.id, offered_card_ids=[card.id]),
        )
    with pytest.raises(AppError):
        await trade_service.create_offer(
            db_session, other, TradeCreateRequest(receiver_id=seller.id, requested_card_ids=[card.id]),
        )


async def test_bid_escrows_and_outbid_is_refunded(db_session, config):
    seller, a, b = await _user(db_session), await _user(db_session, balance=1000), await _user(db_session, balance=1000)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card, start=100)

    with pytest.raises(ForbiddenError):
        await _bid(db_session, seller, lot.id, 100)
    with pytest.raises(ConflictError):
        await _bid(db_session, a, lot.id, 99)

    res = await _bid(db_session, a, lot.id, 100)
    assert res.new_balance == 900 and res.lot.i_am_leading
    # Min raise = max(10 coins, 5 %) → 110.
    assert res.lot.min_next_bid == 110
    with pytest.raises(ConflictError):
        await _bid(db_session, a, lot.id, 200)  # already leading
    with pytest.raises(ConflictError):
        await _bid(db_session, b, lot.id, 109)

    res = await _bid(db_session, b, lot.id, 150)
    assert res.new_balance == 850
    assert await _balance(db_session, a.id) == 1000  # refunded in full
    types = (await db_session.execute(
        select(CoinTransaction.type, CoinTransaction.amount).where(CoinTransaction.user_id == a.id).order_by(CoinTransaction.id)
    )).all()
    assert types == [(TransactionType.auction_bid, -100), (TransactionType.auction_refund, 100)]
    outbid = (await db_session.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == a.id, Notification.type == NotificationType.auction_outbid,
        )
    )).scalar_one()
    assert outbid == 1


async def test_insufficient_balance_rejects_bid(db_session, config):
    seller, poor = await _user(db_session), await _user(db_session, balance=50)
    lot = await _list(db_session, seller, await _card(db_session, seller), start=100)
    with pytest.raises(AppError):
        await _bid(db_session, poor, lot.id, 100)
    assert await _balance(db_session, poor.id) == 50


async def test_bid_idempotency_key_replays(db_session, config):
    seller, a = await _user(db_session), await _user(db_session, balance=1000)
    lot = await _list(db_session, seller, await _card(db_session, seller), start=100)
    key = _key()
    first = await _bid(db_session, a, lot.id, 100, key=key)
    second = await _bid(db_session, a, lot.id, 100, key=key)
    assert first.new_balance == second.new_balance == 900
    bids = (await db_session.execute(select(func.count(AuctionBid.id)).where(AuctionBid.lot_id == lot.id))).scalar_one()
    assert bids == 1


async def test_close_with_bids_transfers_card_and_burns_fee(db_session, config):
    seller = await _user(db_session, balance=0)
    buyer = await _user(db_session, balance=1000)
    card = await _card(db_session, seller, stars=2, star_rating_bonus=2, skill_code=None)
    lot = await _list(db_session, seller, card, start=100)
    await _bid(db_session, buyer, lot.id, 200)
    await _expire(db_session, lot.id)

    assert await auction_service.sweep_due(db_session) == 1
    assert await auction_service.sweep_due(db_session) == 0  # never twice

    lot_row = await db_session.get(AuctionLot, lot.id)
    await db_session.refresh(lot_row)
    assert (lot_row.status, lot_row.winner_id, lot_row.final_price, lot_row.fee_amount) == ("sold", buyer.id, 200, 20)
    await db_session.refresh(card)
    assert card.owner_id == buyer.id and not card.is_locked_in_trade
    assert (card.stars, card.star_rating_bonus) == (2, 2)  # the copy's state travels
    assert await _balance(db_session, seller.id) == 180  # 10 % burnt
    assert await _balance(db_session, buyer.id) == 800
    won = (await db_session.execute(select(AuctionBid.status).where(AuctionBid.lot_id == lot.id))).scalar_one()
    assert won == "won"


async def test_close_without_bids_returns_card(db_session, config):
    seller = await _user(db_session)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card)
    await _expire(db_session, lot.id)
    out = await auction_service.get_lot(db_session, seller, lot.id)  # lazy sweep on read
    assert out.status == "expired"
    await db_session.refresh(card)
    assert card.owner_id == seller.id and not card.is_locked_in_trade


async def test_buy_now_settles_and_refunds_leader(db_session, config):
    seller = await _user(db_session, balance=0)
    a, b = await _user(db_session, balance=1000), await _user(db_session, balance=1000)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card, start=100, buy_now=500)

    with pytest.raises(ConflictError):  # a bid at/above buy-now must be a purchase
        await _bid(db_session, a, lot.id, 500)
    await _bid(db_session, a, lot.id, 100)
    with pytest.raises(ConflictError):
        await auction_service.buy_now(db_session, b, lot.id, AuctionBuyNowIn(expected_price=400))

    res = await auction_service.buy_now(db_session, b, lot.id, AuctionBuyNowIn(expected_price=500))
    assert res.lot.status == "sold" and res.lot.i_won and res.new_balance == 500
    assert await _balance(db_session, a.id) == 1000
    assert await _balance(db_session, seller.id) == 450
    await db_session.refresh(card)
    assert card.owner_id == b.id

    # Replay of the same purchase is a no-op, not a second debit.
    again = await auction_service.buy_now(db_session, b, lot.id, AuctionBuyNowIn(expected_price=500))
    assert again.new_balance == 500
    with pytest.raises(ConflictError):
        await _bid(db_session, a, lot.id, 600)


async def test_anti_sniping_extends_last_minute_bid(db_session, config):
    seller, a = await _user(db_session), await _user(db_session)
    lot = await _list(db_session, seller, await _card(db_session, seller))
    row = await db_session.get(AuctionLot, lot.id)
    row.ends_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    await db_session.commit()

    res = await _bid(db_session, a, lot.id, 100)
    left = (res.lot.ends_at - datetime.now(timezone.utc)).total_seconds()
    assert 100 < left <= 120


async def test_cancel_only_without_bids(db_session, config):
    seller, a = await _user(db_session), await _user(db_session)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card)
    with pytest.raises(ForbiddenError):
        await auction_service.cancel_lot(db_session, a, lot.id)
    await _bid(db_session, a, lot.id, 100)
    with pytest.raises(ConflictError):
        await auction_service.cancel_lot(db_session, seller, lot.id)

    card2 = await _card(db_session, seller)
    lot2 = await _list(db_session, seller, card2)
    out = await auction_service.cancel_lot(db_session, seller, lot2.id)
    assert out.status == "cancelled"
    await db_session.refresh(card2)
    assert not card2.is_locked_in_trade


async def test_admin_remove_refunds_and_logs(db_session, config):
    seller, a = await _user(db_session), await _user(db_session, balance=1000)
    admin = await _user(db_session)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card)
    await _bid(db_session, a, lot.id, 300)

    out = await auction_service.admin_remove(db_session, admin, lot.id, "подозрение на отмывание")
    assert out.status == "removed"
    assert await _balance(db_session, a.id) == 1000
    await db_session.refresh(card)
    assert card.owner_id == seller.id and not card.is_locked_in_trade
    from app.models.admin_action import AdminAction
    logged = (await db_session.execute(select(AdminAction).where(AdminAction.action == "auction_remove_lot"))).scalar_one()
    assert logged.entity_id == lot.id


async def test_disabled_market_blocks_new_activity_but_not_cancel(db_session, config):
    seller, a = await _user(db_session), await _user(db_session)
    card = await _card(db_session, seller)
    lot = await _list(db_session, seller, card)
    config.auction_enabled = False
    await db_session.commit()
    with pytest.raises(ConflictError):
        await _list(db_session, seller, await _card(db_session, seller))
    with pytest.raises(ConflictError):
        await _bid(db_session, a, lot.id, 100)
    assert (await auction_service.cancel_lot(db_session, seller, lot.id)).status == "cancelled"


async def test_new_accounts_and_trade_bans_cannot_trade(db_session, config):
    seller = await _user(db_session)
    fresh = await _user(db_session, created_at=datetime.now(timezone.utc))
    lot = await _list(db_session, seller, await _card(db_session, seller))
    with pytest.raises(ForbiddenError):
        await _bid(db_session, fresh, lot.id, 100)
    with pytest.raises(ForbiddenError):
        await _list(db_session, fresh, await _card(db_session, fresh))
    info = await auction_service.get_info(db_session, fresh)
    assert info.restriction

    banned = await _user(db_session)
    banned.is_trade_banned = True
    await db_session.commit()
    with pytest.raises(ForbiddenError):
        await _bid(db_session, banned, lot.id, 100)


async def test_win_limit_per_seller(db_session, config):
    config.auction_max_wins_per_seller_daily = 1
    await db_session.commit()
    seller, a = await _user(db_session), await _user(db_session)
    lot1 = await _list(db_session, seller, await _card(db_session, seller))
    lot2 = await _list(db_session, seller, await _card(db_session, seller))
    await _bid(db_session, a, lot1.id, 100)
    with pytest.raises(ConflictError):  # already leading one lot of this seller
        await _bid(db_session, a, lot2.id, 100)


async def test_active_lot_limit(db_session, config):
    config.auction_max_active_lots = 1
    await db_session.commit()
    seller = await _user(db_session)
    await _list(db_session, seller, await _card(db_session, seller))
    with pytest.raises(ConflictError):
        await _list(db_session, seller, await _card(db_session, seller))


async def test_search_filters(db_session, config):
    seller, viewer = await _user(db_session), await _user(db_session)
    starred = await _card(db_session, seller, stars=2)
    plain = await _card(db_session, seller)
    await _list(db_session, seller, starred, start=300)
    await _list(db_session, seller, plain, start=100)

    everything = await auction_service.list_lots(db_session, viewer)
    assert everything.total == 2
    by_stars = await auction_service.list_lots(db_session, viewer, min_stars=1)
    assert [l.card.id for l in by_stars.items] == [starred.id]
    cheap = await auction_service.list_lots(db_session, viewer, max_price=150)
    assert [l.card.id for l in cheap.items] == [plain.id]
    by_price = await auction_service.list_lots(db_session, viewer, sort="price_desc")
    assert [l.card.id for l in by_price.items] == [starred.id, plain.id]
    by_name = await auction_service.list_lots(db_session, viewer, search=plain.player.last_name)
    assert by_name.total == 1


async def test_http_flow(client, db_session, config):
    """Smoke test through the API as the dev-mode user."""
    headers = {"X-Dev-Mode": "true"}
    me = (await client.post("/api/v1/auth/session", headers=headers)).json()
    assert me
    info = await client.get("/api/v1/auction/info", headers=headers)
    assert info.status_code == 200 and info.json()["enabled"] is True
    flags = await client.get("/api/v1/feature-flags", headers=headers)
    assert flags.json()["auction_enabled"] is True
    lots = await client.get("/api/v1/auction/lots", headers=headers)
    assert lots.status_code == 200 and lots.json()["total"] == 0
