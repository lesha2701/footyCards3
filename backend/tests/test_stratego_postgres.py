"""Stratego concurrency against a REAL PostgreSQL (row locks). SQLite ignores
SELECT ... FOR UPDATE, so these only run when STRATEGO_PG_URL points at a
database already migrated to head, e.g.:

    STRATEGO_PG_URL=postgresql+asyncpg://postgres:pw@localhost:5446/footycards \\
        pytest tests/test_stratego_postgres.py -v

Each test creates its own users/cards, so the database can be reused.
"""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity, StrategoMatchStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.stratego import StrategoMatch
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import stratego_service

PG_URL = os.environ.get("STRATEGO_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="STRATEGO_PG_URL not set (needs real PostgreSQL)")


@pytest.fixture(autouse=True)
def _fresh_schema():
    # Overrides conftest's SQLite create_all/drop_all: the PG database is
    # migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg():
    engine = create_async_engine(PG_URL, pool_size=10)
    async with async_sessionmaker(bind=engine)() as s:
        if await s.get(GameConfig, 1) is None:
            s.add(GameConfig(id=1))
            await s.commit()
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _user_with_cards(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=0)
        s.add(user)
        await s.flush()
        for rating, pos in ((90, Position.ST), (70, Position.CB), (65, Position.LW), (60, Position.CM), (55, Position.GK)):
            tag = uuid.uuid4().hex[:6]
            player = Player(
                first_name="S", last_name=tag, display_name=f"S {tag}", rating=rating, rarity=Rarity.common,
                country="X", club="Y", position=pos, quick_sell_price=1, is_active=True,
            )
            s.add(player)
            await s.flush()
            s.add(UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed))
        await s.commit()
        return user.id


async def _as(pg, user_id: int, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def test_concurrent_bot_match_creation_starts_only_one(pg):
    uid = await _user_with_cards(pg)
    results = await asyncio.gather(*[_as(pg, uid, stratego_service.create_bot_match) for _ in range(4)])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        active = (await s.execute(
            select(func.count()).select_from(StrategoMatch)
            .where(StrategoMatch.user_id == uid, StrategoMatch.status == StrategoMatchStatus.in_progress)
        )).scalar_one()
        user = await s.get(User, uid)
        assert active == 1 and user.stratego_hourly_attempts == 1


async def test_concurrent_forfeits_settle_once(pg):
    uid = await _user_with_cards(pg)
    match = await _as(pg, uid, stratego_service.create_bot_match)
    # Make the user the winner-by-forfeit path irrelevant: race two forfeits;
    # exactly one may finish the match, the other must see it finished.
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: stratego_service.forfeit_match(s, u, match.id)) for _ in range(3)
    ])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        m = await s.get(StrategoMatch, match.id)
        assert m.status == StrategoMatchStatus.finished


async def test_concurrent_pvp_finish_pays_each_side_once(pg):
    a = await _user_with_cards(pg)
    b = await _user_with_cards(pg)
    created = await _as(pg, a, lambda s, u: stratego_service.create_challenge(s, u, b))
    await _as(pg, b, lambda s, u: stratego_service.accept_challenge(s, u, created.id))
    # Both players forfeit at the same instant: one wins the race, and the
    # winner (the other side) is rewarded exactly once.
    await asyncio.gather(
        _as(pg, a, lambda s, u: stratego_service.forfeit_match(s, u, created.id)),
        _as(pg, b, lambda s, u: stratego_service.forfeit_match(s, u, created.id)),
    )
    async with pg() as s:
        txs = (await s.execute(
            select(CoinTransaction).where(
                CoinTransaction.type == TransactionType.stratego_reward,
                or_(CoinTransaction.user_id == a, CoinTransaction.user_id == b),
            )
        )).scalars().all()
        assert len(txs) == 1
