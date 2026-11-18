"""«Воспитанник Академии» concurrency against a REAL PostgreSQL (row locks,
partial unique indexes). SQLite ignores SELECT ... FOR UPDATE, so these run
on the `real_pg` fixture (tests/conftest.py): a dedicated `*_test` database,
migrated to head on first use; every row a test creates is deleted on
teardown. See CLAUDE.md → Backend checks.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppError
from app.models.academy_prospect import AcademyProspect, ProspectLedger
from app.models.enums import Position
from app.models.game_config import GameConfig
from app.models.user import User
from app.services import prospect_life, prospect_service


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


async def _owner(pg, balance: int, days_old: int = 0) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=balance)
        s.add(user)
        await s.flush()
        s.add(AcademyProspect(
            user_id=user.id, name="Кид", number=9, position=Position.ST, foot="right", appearance={}, potential=3,
            xp=300_000, rival_seed=3, cosmetics={"owned": ["bg_yard"]}, memories=[], stats={}, specs=[],
            created_at=datetime.now(timezone.utc) - timedelta(days=days_old),
        ))
        await s.commit()
        return user.id


async def test_two_buys_of_one_item_charge_once(pg):
    uid = await _owner(pg, balance=10_000)
    price = prospect_service.cfg(SimpleConfig())["cosmetics"]["bg_gym"]["coins"]

    async def buy():
        async with pg() as s:
            user = await s.get(User, uid)
            try:
                await prospect_service.buy_cosmetic(s, user, "bg_gym")
                return True
            except (AppError, IntegrityError):
                await s.rollback()
                return False

    results = await asyncio.gather(buy(), buy())
    assert sorted(results) == [False, True]
    async with pg() as s:
        assert (await s.get(User, uid)).balance == 10_000 - price
        assert (await s.execute(select(func.count(ProspectLedger.id)).where(ProspectLedger.user_id == uid))).scalar_one() == 1


async def test_two_graduations_at_once_make_one_graduate(pg):
    uid = await _owner(pg, balance=0, days_old=100)

    async def go():
        async with pg() as s:
            user = await s.get(User, uid)
            try:
                await prospect_life.graduate(s, user)
                return True
            except (AppError, IntegrityError):
                await s.rollback()
                return False

    results = await asyncio.gather(go(), go())
    assert sorted(results) == [False, True]
    async with pg() as s:
        rows = (await s.execute(select(AcademyProspect.status).where(AcademyProspect.user_id == uid))).scalars().all()
        assert rows == ["graduate"]
        coins = prospect_service.cfg(await s.get(GameConfig, 1))["graduation_coins"]
        assert (await s.get(User, uid)).balance == coins


async def test_one_growing_child_per_user(pg):
    uid = await _owner(pg, balance=0)
    async with pg() as s:
        s.add(AcademyProspect(user_id=uid, name="Второй", number=8, position=Position.CM, foot="right", appearance={},
                              potential=3, rival_seed=4, cosmetics={}, memories=[], stats={}, specs=[]))
        with pytest.raises(IntegrityError):
            await s.commit()


class SimpleConfig:
    prospect: dict = {}
