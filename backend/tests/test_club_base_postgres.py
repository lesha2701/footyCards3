"""«Клубная база» concurrency against a REAL PostgreSQL (row locks, SKIP
LOCKED and unique constraints). Runs on the `real_pg` fixture
(tests/conftest.py): a dedicated `*_test` database, migrated to head, every
created row removed on teardown."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.club_base import ClubBaseLedger, UserClubBase
from app.models.enums import NotificationType, TransactionType
from app.models.game_config import GameConfig
from app.models.notification import Notification
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import academy_service, club_base_service


@pytest.fixture(autouse=True)
def _fresh_schema():
    # The PG database is migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg(real_pg):
    async with real_pg() as s:
        config = await s.get(GameConfig, 1)
        if config is None:
            s.add(GameConfig(id=1))
        else:
            config.club_base_enabled = True
            config.academy_enabled = True
        await s.commit()
    yield real_pg


async def _user(pg, balance: int = 100_000, levels: dict | None = None, **base_fields) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=balance)
        s.add(user)
        await s.flush()
        if levels is not None:
            s.add(UserClubBase(user_id=user.id, levels=levels, total_level=sum(levels.values()), appearance={},
                               income_accrued=0, **base_fields))
        await s.commit()
        return user.id


async def _call(pg, fn, user_id: int, *args):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            await fn(s, user, *args)
            return "ok"
        except AppError as exc:
            await s.rollback()
            return exc.code


async def _count(pg, model, *where) -> int:
    async with pg() as s:
        return (await s.execute(select(func.count()).select_from(model).where(*where))).scalar_one()


async def test_concurrent_upgrades_start_one_construction_and_charge_once(pg):
    uid = await _user(pg)
    results = await asyncio.gather(*[
        _call(pg, club_base_service.start_upgrade, uid, "hq", f"k{i}") for i in range(6)
    ])
    assert results.count("ok") == 1
    async with pg() as s:
        user = await s.get(User, uid)
        assert user.balance == 100_000 - 700
    assert await _count(pg, ClubBaseLedger, ClubBaseLedger.user_id == uid, ClubBaseLedger.kind == "upgrade") == 1


async def test_same_idempotency_key_is_charged_once(pg):
    uid = await _user(pg)
    results = await asyncio.gather(*[
        _call(pg, club_base_service.start_upgrade, uid, "hq", "same-key") for _ in range(5)
    ])
    assert set(results) == {"ok"}  # the rest replay the first
    async with pg() as s:
        assert (await s.get(User, uid)).balance == 99_300
    assert await _count(pg, CoinTransaction, CoinTransaction.user_id == uid,
                        CoinTransaction.type == TransactionType.club_base_upgrade) == 1


async def test_base_and_academy_race_for_the_one_queue(pg):
    uid = await _user(pg, levels={"hq": 1})
    results = await asyncio.gather(
        _call(pg, club_base_service.start_upgrade, uid, "stadium", "b"),
        _call(pg, academy_service.start_upgrade, uid, "scout", "a"),
        _call(pg, club_base_service.start_upgrade, uid, "medical", "c"),
        _call(pg, academy_service.start_upgrade, uid, "hall", "d"),
    )
    assert results.count("ok") == 1


async def test_concurrent_income_claims_pay_once(pg):
    since = datetime.now(timezone.utc) - timedelta(days=2, minutes=5)
    uid = await _user(pg, balance=0, levels={"hq": 1, "marketing": 1, "shop": 1}, income_since=since)
    results = await asyncio.gather(*[
        _call(pg, club_base_service.claim_income, uid, f"c{i}") for i in range(6)
    ])
    assert results.count("ok") == 1
    async with pg() as s:
        assert (await s.get(User, uid)).balance == 70
    assert await _count(pg, CoinTransaction, CoinTransaction.user_id == uid,
                        CoinTransaction.type == TransactionType.club_base_income) == 1


async def test_sweeps_and_a_read_complete_a_construction_once(pg):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    uid = await _user(pg, levels={"hq": 1}, building_code="hq", building_to_level=2,
                      build_started_at=past - timedelta(hours=12), build_ends_at=past)

    async def sweep():
        async with pg() as s:
            return await club_base_service.sweep_due(s)

    async def read():
        async with pg() as s:
            await club_base_service.get_state(s, await s.get(User, uid))
            return 0

    await asyncio.gather(sweep(), sweep(), read(), sweep(), read())
    async with pg() as s:
        base = await s.get(UserClubBase, uid)
        assert base.levels == {"hq": 2} and base.building_code is None
    assert await _count(pg, ClubBaseLedger, ClubBaseLedger.user_id == uid, ClubBaseLedger.kind == "complete") == 1
    assert await _count(pg, Notification, Notification.user_id == uid,
                        Notification.type == NotificationType.club_base_built) <= 1
