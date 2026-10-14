"""Stratego concurrency against a REAL PostgreSQL (row locks). SQLite ignores
SELECT ... FOR UPDATE, so these run on the `real_pg` fixture (tests/conftest.py):
a dedicated `*_test` database, created and migrated to head
on first use, never the app's own; every row a test creates is deleted on
teardown. See CLAUDE.md → Backend checks.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import func, or_, select

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity, StrategoMatchStatus, TransactionType
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.stratego import StrategoMatch
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import stratego_service

@pytest.fixture(autouse=True)
def _fresh_schema():
    # Overrides conftest's SQLite create_all/drop_all: the PG database is
    # migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg(real_pg):
    async with real_pg() as s:
        if await s.get(GameConfig, 1) is None:
            s.add(GameConfig(id=1))
            await s.commit()
    yield real_pg


async def _user_with_cards(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=0)
        s.add(user)
        await s.flush()
        # A full default (8×8, 13 card pieces) squad that meets the rarity
        # rules: 4 rare + 2 common minimum, roles at most epic.
        spec = [
            (90, Position.ST, Rarity.epic), (80, Position.CB, Rarity.epic), (79, Position.LB, Rarity.rare),
            (78, Position.RB, Rarity.rare), (77, Position.LW, Rarity.epic), (76, Position.RW, Rarity.rare),
            (75, Position.CM, Rarity.rare), (70, Position.CAM, Rarity.epic), (69, Position.GK, Rarity.common),
            (68, Position.CDM, Rarity.common), (67, Position.LM, Rarity.epic), (66, Position.RM, Rarity.epic),
            (65, Position.ST, Rarity.epic),
        ]
        for rating, pos, rarity in spec:
            tag = uuid.uuid4().hex[:6]
            player = Player(
                first_name="S", last_name=tag, display_name=f"S {tag}", rating=rating, rarity=rarity,
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
