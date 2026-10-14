"""«Звёзды карточек» concurrency against a REAL PostgreSQL (row locks).
SQLite ignores SELECT ... FOR UPDATE, so these only run when
CARD_STARS_PG_URL points at a database already migrated to head, e.g.:

    CARD_STARS_PG_URL=postgresql+asyncpg://postgres:pw@localhost:5446/footycards \\
        pytest tests/test_card_stars_postgres.py -v

Each test creates its own users/cards, so the database can be reused.
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppError
from app.models.card import CardStarLedger, UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.user import User
from app.schemas.card_star import CardStarFeedRequest
from app.services import card_star_service

PG_URL = os.environ.get("CARD_STARS_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="CARD_STARS_PG_URL not set (needs real PostgreSQL)")


@pytest.fixture(autouse=True)
def _fresh_schema():
    # Overrides conftest's SQLite create_all/drop_all: the PG database is
    # migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg():
    engine = create_async_engine(PG_URL, pool_size=10)
    async with async_sessionmaker(bind=engine)() as s:
        config = await s.get(GameConfig, 1)
        if config is None:
            config = GameConfig(id=1)
            s.add(config)
        config.card_stars_enabled = True
        config.card_star_dupes_per_level = {r: [2, 3, 5] for r in ("common", "rare", "epic", "legendary")}
        config.card_star_coin_cost = {r: [100, 200, 400] for r in ("common", "rare", "epic", "legendary")}
        await s.commit()
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _user_with_copies(pg, copies: int, balance: int) -> tuple[int, list[int]]:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=balance)
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="S", last_name=tag, display_name=f"S {tag}", rating=80, rarity=Rarity.common,
            country="X", club="Y", position=Position.ST, quick_sell_price=1, is_active=True,
        )
        s.add_all([user, player])
        await s.flush()
        cards = [
            UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=i + 1)
            for i in range(copies)
        ]
        s.add_all(cards)
        await s.commit()
        return user.id, [c.id for c in cards]


async def _as(pg, user_id: int, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def test_concurrent_all_free_feeds_never_double_count(pg):
    uid, ids = await _user_with_copies(pg, copies=12, balance=10_000)
    target = ids[0]
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: card_star_service.feed(s, u, target, CardStarFeedRequest(all_free=True)))
        for _ in range(4)
    ])
    consumed = sum(r.cards_consumed for r in results if not isinstance(r, AppError))
    async with pg() as s:
        card = await s.get(UserCard, target)
        user = await s.get(User, uid)
        left = (await s.execute(
            select(func.count()).select_from(UserCard).where(UserCard.player_id == card.player_id)
        )).scalar_one()
        ledger = (await s.execute(
            select(func.sum(CardStarLedger.cards_consumed)).where(CardStarLedger.user_id == uid)
        )).scalar_one()
    # 2 + 3 + 5 = 10 duplicates make the max; exactly those were burnt once.
    assert consumed == ledger == 10
    assert (card.stars, card.star_progress, card.star_rating_bonus) == (3, 0, 3)
    assert left == 12 - 10
    assert user.balance == 10_000 - 700


async def test_concurrent_claims_charge_once(pg):
    uid, ids = await _user_with_copies(pg, copies=3, balance=50)
    target = ids[0]
    fed = await _as(pg, uid, lambda s, u: card_star_service.feed(
        s, u, target, CardStarFeedRequest(material_card_ids=ids[1:], idempotency_key="f"),
    ))
    # Not enough coins: the duplicates are banked, the star waits.
    assert not isinstance(fed, AppError) and fed.stars_gained == 0 and fed.state.claimable
    async with pg() as s:
        user = await s.get(User, uid)
        user.balance = 150
        await s.commit()
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: card_star_service.claim(s, u, target, None)) for _ in range(4)
    ])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        user = await s.get(User, uid)
        card = await s.get(UserCard, target)
        assert user.balance == 50 and (card.stars, card.star_progress) == (1, 0)
