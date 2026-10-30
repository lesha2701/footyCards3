"""«Трансферный рынок» concurrency against a REAL PostgreSQL (row locks, SKIP
LOCKED). SQLite ignores both, so these run on the `real_pg` fixture
(tests/conftest.py): a dedicated `*_test` database, created and migrated to head
on first use, never the app's own; every row a test creates is deleted on
teardown. See CLAUDE.md → Backend checks.

Every scenario checks money conservation: balances + the escrowed leading bid
+ burnt fees == what the participants started with.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.auction import AgentLicense, AuctionBid, AuctionLot
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.user import User
from app.schemas.auction import AuctionBidIn, AuctionBuyNowIn, AuctionLotCreateIn
from app.services import auction_service

START = 10_000
OLD = datetime.now(timezone.utc) - timedelta(days=60)


@pytest.fixture(autouse=True)
def _fresh_schema():
    # Overrides conftest's SQLite create_all/drop_all: the PG database is
    # migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg(real_pg):
    async with real_pg() as s:
        config = await s.get(GameConfig, 1)
        if config is None:
            config = GameConfig(id=1)
            s.add(config)
        config.auction_enabled = True
        config.auction_fee_pct = 10
        config.auction_min_account_age_days = 3
        config.auction_max_wins_per_seller_daily = 100
        config.auction_max_active_lots = 5
        config.auction_snipe_window_seconds = 120
        config.auction_snipe_extend_seconds = 120
        config.agent_license_enabled = True
        config.agent_license_stars = 99
        config.agent_license_days = 30
        config.agent_license_min_account_age_days = 30
        config.trade_verified_min_stars = 0
        await s.commit()
    yield real_pg


async def _user(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=START, created_at=OLD)
        s.add(user)
        await s.commit()
        return user.id


async def _make_agent(pg, user_id: int) -> None:
    async with pg() as s:
        if await s.get(AgentLicense, user_id) is None:
            s.add(AgentLicense(
                user_id=user_id, expires_at=datetime.now(timezone.utc) + timedelta(days=30), purchases=1, stars_total=99,
            ))
            await s.commit()


async def _lot(pg, seller_id: int, buy_now=None) -> tuple[int, int]:
    await _make_agent(pg, seller_id)
    async with pg() as s:
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="A", last_name=tag, display_name=f"A {tag}", rating=80, rarity=Rarity.rare, country="X",
            club="Y", position=Position.ST, quick_sell_price=10, is_active=True,
        )
        s.add(player)
        await s.flush()
        cards = [UserCard(owner_id=seller_id, player_id=player.id, source=CardSource.seed, serial_number=i + 1) for i in range(2)]
        s.add_all(cards)
        await s.commit()
        seller = await s.get(User, seller_id)
        lot = await auction_service.create_lot(
            s, seller, AuctionLotCreateIn(user_card_id=cards[0].id, start_price=100, buy_now_price=buy_now, duration_hours=1),
        )
        return lot.id, cards[0].id


async def _as(pg, user_id: int, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


def _bid(lot_id, amount, key=None):
    return lambda s, u: auction_service.place_bid(
        s, u, lot_id, AuctionBidIn(amount=amount, idempotency_key=key or uuid.uuid4().hex),
    )


async def _expire(pg, lot_id):
    async with pg() as s:
        lot = await s.get(AuctionLot, lot_id)
        lot.ends_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await s.commit()


async def _assert_conserved(pg, lot_id: int, user_ids: list[int]):
    async with pg() as s:
        lot = await s.get(AuctionLot, lot_id)
        balances = (await s.execute(select(func.sum(User.balance)).where(User.id.in_(user_ids)))).scalar_one()
        escrow = lot.current_bid if lot.status == "active" and lot.current_bid else 0
        burnt = lot.fee_amount or 0
        assert balances + escrow + burnt == START * len(user_ids)
        leading = (await s.execute(
            select(func.count()).select_from(AuctionBid).where(AuctionBid.lot_id == lot_id, AuctionBid.status == "leading")
        )).scalar_one()
        assert leading == (1 if lot.status == "active" and lot.current_bidder_id else 0)
        return lot


async def test_same_amount_bids_race_accepts_exactly_one(pg):
    seller = await _user(pg)
    bidders = [await _user(pg) for _ in range(6)]
    lot_id, _ = await _lot(pg, seller)
    results = await asyncio.gather(*[_as(pg, uid, _bid(lot_id, 100)) for uid in bidders])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    lot = await _assert_conserved(pg, lot_id, [seller, *bidders])
    assert lot.current_bid == 100 and lot.bid_count == 1


async def test_escalating_bid_storm_keeps_money_consistent(pg):
    seller = await _user(pg)
    bidders = [await _user(pg) for _ in range(5)]
    lot_id, _ = await _lot(pg, seller)
    jobs = [_as(pg, bidders[i % 5], _bid(lot_id, 100 + 20 * i)) for i in range(20)]
    await asyncio.gather(*jobs)
    lot = await _assert_conserved(pg, lot_id, [seller, *bidders])
    assert lot.current_bidder_id in bidders
    async with pg() as s:
        top = (await s.execute(select(func.max(AuctionBid.amount)).where(AuctionBid.lot_id == lot_id))).scalar_one()
    assert top == lot.current_bid


async def test_same_idempotency_key_escrows_once(pg):
    seller, bidder = await _user(pg), await _user(pg)
    lot_id, _ = await _lot(pg, seller)
    key = uuid.uuid4().hex
    await asyncio.gather(*[_as(pg, bidder, _bid(lot_id, 150, key)) for _ in range(4)])
    async with pg() as s:
        assert (await s.get(User, bidder)).balance == START - 150
        assert (await s.execute(select(func.count(AuctionBid.id)).where(AuctionBid.lot_id == lot_id))).scalar_one() == 1


async def test_parallel_sweeps_and_reads_close_once(pg):
    seller, bidder = await _user(pg), await _user(pg)
    lot_id, card_id = await _lot(pg, seller)
    await _as(pg, bidder, _bid(lot_id, 300))
    await _expire(pg, lot_id)

    async def sweep():
        async with pg() as s:
            return await auction_service.sweep_due(s)

    results = await asyncio.gather(
        sweep(), sweep(), sweep(),
        _as(pg, bidder, lambda s, u: auction_service.get_lot(s, u, lot_id)),
        _as(pg, seller, lambda s, u: auction_service.my_lots(s, u)),
    )
    lot = await _assert_conserved(pg, lot_id, [seller, bidder])
    assert lot.status == "sold" and lot.final_price == 300 and lot.fee_amount == 30
    async with pg() as s:
        assert (await s.get(User, seller)).balance == START + 270
        card = await s.get(UserCard, card_id)
        assert card.owner_id == bidder and not card.is_locked_in_trade
    assert sum(r for r in results[:3]) <= 1


async def test_bid_racing_close_either_wins_cleanly(pg):
    """A bid and the sweep hit a lot that ends right now: either the bid lands
    first (and, by anti-sniping, pushes the end out) or the sweep closes the
    lot and the bid is refused — never both, never money lost."""
    seller, a, b = await _user(pg), await _user(pg), await _user(pg)
    lot_id, card_id = await _lot(pg, seller)
    await _as(pg, a, _bid(lot_id, 100))
    async with pg() as s:
        lot = await s.get(AuctionLot, lot_id)
        lot.ends_at = datetime.now(timezone.utc) + timedelta(milliseconds=150)
        await s.commit()
    await asyncio.sleep(0.15)

    async def sweep():
        async with pg() as s:
            return await auction_service.sweep_due(s)

    results = await asyncio.gather(sweep(), _as(pg, b, _bid(lot_id, 200)), sweep())
    lot = await _assert_conserved(pg, lot_id, [seller, a, b])
    bid_result = results[1]
    if isinstance(bid_result, AppError):
        assert lot.status == "sold" and lot.winner_id == a
    else:
        assert lot.status == "active" and lot.current_bidder_id == b
        assert lot.ends_at > datetime.now(timezone.utc)


async def test_buy_now_racing_bids_sells_once(pg):
    seller = await _user(pg)
    buyers = [await _user(pg) for _ in range(3)]
    bidders = [await _user(pg) for _ in range(3)]
    lot_id, card_id = await _lot(pg, seller, buy_now=1000)
    jobs = [
        _as(pg, uid, lambda s, u: auction_service.buy_now(s, u, lot_id, AuctionBuyNowIn(expected_price=1000)))
        for uid in buyers
    ] + [_as(pg, uid, _bid(lot_id, 100 + 50 * i)) for i, uid in enumerate(bidders)]
    results = await asyncio.gather(*jobs)
    bought = [r for r in results[:3] if not isinstance(r, AppError)]
    assert len(bought) == 1
    lot = await _assert_conserved(pg, lot_id, [seller, *buyers, *bidders])
    assert lot.status == "sold" and lot.final_price == 1000
    async with pg() as s:
        assert (await s.get(User, seller)).balance == START + 900
        card = await s.get(UserCard, card_id)
        assert card.owner_id == lot.winner_id and lot.winner_id in buyers


async def test_concurrent_listing_of_one_card_creates_one_lot(pg):
    seller = await _user(pg)
    await _make_agent(pg, seller)
    async with pg() as s:
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="A", last_name=tag, display_name=f"A {tag}", rating=80, rarity=Rarity.rare, country="X",
            club="Y", position=Position.ST, quick_sell_price=10, is_active=True,
        )
        s.add(player)
        await s.flush()
        cards = [UserCard(owner_id=seller, player_id=player.id, source=CardSource.seed, serial_number=i + 1) for i in range(2)]
        s.add_all(cards)
        await s.commit()
        card_id = cards[0].id
    payload = AuctionLotCreateIn(user_card_id=card_id, start_price=100, duration_hours=1)
    results = await asyncio.gather(*[
        _as(pg, seller, lambda s, u: auction_service.create_lot(s, u, payload)) for _ in range(4)
    ])
    ids = {r.id for r in results if not isinstance(r, AppError)}
    assert len(ids) == 1
    async with pg() as s:
        count = (await s.execute(
            select(func.count(AuctionLot.id)).where(AuctionLot.user_card_id == card_id, AuctionLot.status == "active")
        )).scalar_one()
        assert count == 1


async def test_concurrent_license_deliveries_both_count(pg):
    """Two paid invoices of one player delivered at the same moment (bot +
    retry loop): the user row lock serializes them, so the row is created
    once and both purchases add their days."""
    from app.models.pack import StarsInvoice
    from app.services import shop_product_service

    uid = await _user(pg)
    tokens = []
    async with pg() as s:
        for _ in range(2):
            token = uuid.uuid4().hex
            s.add(StarsInvoice(user_id=uid, payload_token=token, stars_amount=99, shop_product="agent_license"))
            tokens.append(token)
        await s.commit()

    async def deliver(token):
        async with pg() as s:
            user = await s.get(User, uid)
            invoice = (await s.execute(select(StarsInvoice).where(StarsInvoice.payload_token == token))).scalar_one()
            await shop_product_service.deliver(s, user, invoice, f"charge-{token}")
            await s.commit()

    started = datetime.now(timezone.utc)
    await asyncio.gather(*[deliver(t) for t in tokens])
    async with pg() as s:
        lic = await s.get(AgentLicense, uid)
        assert (lic.purchases, lic.stars_total) == (2, 198)
        assert lic.expires_at - started >= timedelta(days=59, hours=23)
