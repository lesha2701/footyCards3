"""«Музы» on real Postgres: parallel requests of one player end consistent —
the daily coins are paid once, one Muse stays active (partial unique index),
one gift is bought once. Every row a test creates is deleted on teardown
(real_pg)."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.exceptions import AppError
from app.models.muse import Muse, MuseAccessory, MuseDailyClaim, UserMuse, UserMuseAccessory
from app.models.user import User
from app.services import muse_service

CONFIG = SimpleNamespace(
    muses_enabled=True, muse_max_stat=6, muse_max_pp=12, muse_max_xp_pct=30, muse_max_daily_coins=1000,
    muse_max_accessory_pct=100, muse_spare_coins={}, muse_date_required=False, muse_inspiration_hours=36, muse_date_coins=150,
    muse_date_games=["memory"],
)


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    # The shared test database's game_config row must not be changed.
    async def fake_get_config(_db):
        return CONFIG

    monkeypatch.setattr(muse_service, "get_config", fake_get_config)
    yield


async def _setup(pg, muses=2):
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Muse", balance=10_000)
        rows = [Muse(name=f"Муза {uuid.uuid4().hex[:6]}", effect="daily_coins", effect_value=100) for _ in range(muses)]
        gift = MuseAccessory(name=f"Сумка {uuid.uuid4().hex[:6]}", boost_pct=10, coins_price=100)
        s.add_all([user, gift, *rows])
        await s.flush()
        owned = [UserMuse(user_id=user.id, muse_id=m.id, is_active=i == 0, source="admin") for i, m in enumerate(rows)]
        s.add_all(owned)
        await s.commit()
        return user.id, [m.id for m in rows], gift.id


async def _as(pg, user_id, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def test_parallel_daily_claims_pay_once(real_pg):
    uid, _muses, _gift = await _setup(real_pg)
    results = await asyncio.gather(*[_as(real_pg, uid, muse_service.claim_daily) for _ in range(4)])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with real_pg() as s:
        assert len((await s.execute(select(MuseDailyClaim).where(MuseDailyClaim.user_id == uid))).scalars().all()) == 1
        assert (await s.get(User, uid)).balance == 10_100


async def test_parallel_switches_leave_one_active(real_pg):
    uid, (a, b), _gift = await _setup(real_pg)
    results = await asyncio.gather(*[
        _as(real_pg, uid, lambda s, u, m=m: muse_service.set_active(s, u, m)) for m in (a, b, a, b, b)
    ])
    assert all(not isinstance(r, Exception) or isinstance(r, AppError) for r in results)
    async with real_pg() as s:
        active = (await s.execute(select(UserMuse).where(UserMuse.user_id == uid, UserMuse.is_active.is_(True)))).unique().scalars().all()
        assert len(active) == 1


async def test_parallel_gift_purchases_buy_once(real_pg):
    uid, (a, _b), gift = await _setup(real_pg)
    results = await asyncio.gather(*[
        _as(real_pg, uid, lambda s, u: muse_service.buy_accessory(s, u, a, gift)) for _ in range(4)
    ])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with real_pg() as s:
        rows = (await s.execute(select(UserMuseAccessory).where(UserMuseAccessory.user_id == uid))).unique().scalars().all()
        assert len(rows) == 1
        assert (await s.get(User, uid)).balance == 9_900
