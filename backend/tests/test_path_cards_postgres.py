"""«Начало пути» concurrency against a REAL PostgreSQL (row locks + unique
constraints). Runs on the `real_pg` fixture (tests/conftest.py): a dedicated
`*_test` database, migrated to head, every created row removed on teardown.
"""
import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.card_path import CardPath, PathAttemptPurchase, PathXpEvent
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.player import Player
from app.models.user import User
from app.services import path_service


@pytest.fixture(autouse=True)
def _fresh_schema():
    # The PG database is migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg(real_pg):
    async with real_pg() as s:
        config = await s.get(GameConfig, 1)
        if config is None:
            config = GameConfig(id=1)
            s.add(config)
        config.path_enabled = True
        config.path_daily_free_arena = 2
        config.path_coin_attempt_prices = [300, 400]
        await s.commit()
    yield real_pg


async def _user_with_path_card(pg, balance: int = 10_000) -> tuple[int, int]:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=balance)
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="P", last_name=tag, display_name=f"P {tag}", rating=60, rarity=Rarity.diamond,
            country="X", club="Y", position=Position.ST, quick_sell_price=1, is_active=True,
            path_talent_code="fighter",
        )
        s.add_all([user, player])
        await s.flush()
        card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed, serial_number=1)
        s.add(card)
        await s.commit()
        return user.id, card.id


async def _award(pg, user_id: int, card_id: int, source_id: str):
    async with pg() as s:
        res = await path_service.award_match(
            s, user_id=user_id, source_type="arena", source_id=source_id,
            entries=[path_service.MatchEntry(card_id, "win")],
        )
        await s.commit()
        return res[0].status


async def test_concurrent_awards_for_the_same_match_count_once(pg):
    uid, cid = await _user_with_path_card(pg)
    statuses = await asyncio.gather(*[_award(pg, uid, cid, "same-match") for _ in range(5)])
    assert statuses.count("awarded") == 1
    async with pg() as s:
        events = (await s.execute(select(func.count(PathXpEvent.id)).where(PathXpEvent.user_card_id == cid))).scalar_one()
        path = await s.get(CardPath, cid)
        assert events == 1 and path.xp == 20 and path.arena_used == 1


async def test_concurrent_awards_never_exceed_the_daily_free_attempts(pg):
    uid, cid = await _user_with_path_card(pg)
    statuses = await asyncio.gather(*[_award(pg, uid, cid, f"m{i}") for i in range(6)])
    assert statuses.count("awarded") == 2 and statuses.count("no_attempts") == 4
    async with pg() as s:
        path = await s.get(CardPath, cid)
        assert path.arena_used == 2 and path.xp == 40


async def test_concurrent_coin_purchases_respect_the_daily_limit_and_charge_once_each(pg):
    uid, cid = await _user_with_path_card(pg, balance=10_000)

    async def buy(key: str):
        async with pg() as s:
            user = await s.get(User, uid)
            try:
                return await path_service.buy_attempt_with_coins(s, user, cid, key)
            except AppError as exc:
                return exc

    results = await asyncio.gather(*[buy(f"key-{i}") for i in range(5)])
    ok = [r for r in results if not isinstance(r, AppError)]
    assert len(ok) == 2
    async with pg() as s:
        user = await s.get(User, uid)
        purchases = (await s.execute(select(func.sum(PathAttemptPurchase.price)).where(PathAttemptPurchase.user_id == uid))).scalar_one()
        path = await s.get(CardPath, cid)
        assert purchases == 700 and user.balance == 10_000 - 700 and path.bought_attempts == 2
