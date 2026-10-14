"""«Футбольный магнат» concurrency against a REAL PostgreSQL (row locks,
SKIP LOCKED). SQLite ignores both, so these run on the `real_pg` fixture
(tests/conftest.py): a dedicated `*_test` database, created and migrated to head
on first use, never the app's own; every row a test creates is deleted on
teardown. See CLAUDE.md → Backend checks.
"""
import asyncio
import copy
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import AppError
from app.models.game_config import GameConfig
from app.models.magnate import MagnateMatch, MagnateSeat
from app.models.user import User
from app.services import magnate_service

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
            s.add(GameConfig(id=1, hourly_game_limit=100))
        else:
            config.hourly_game_limit = 100
        await s.commit()
    yield real_pg


async def _user(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=0)
        s.add(user)
        await s.commit()
        return user.id


async def _as(pg, user_id: int, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def test_concurrent_lobby_joins_never_overfill_a_table(pg):
    async with pg() as s:  # start from no open public lobbies
        for m in (await s.execute(select(MagnateMatch).where(MagnateMatch.mode == "public", MagnateMatch.status == "lobby"))).scalars():
            m.status = "cancelled"
        await s.commit()
    users = [await _user(pg) for _ in range(9)]
    results = await asyncio.gather(*[_as(pg, uid, magnate_service.join_public_lobby) for uid in users])
    ok = [r for r in results if not isinstance(r, AppError)]
    assert len(ok) == len(users)
    async with pg() as s:
        rows = (await s.execute(select(MagnateSeat).where(MagnateSeat.user_id.in_(users)))).scalars().all()
        assert sorted(r.user_id for r in rows) == sorted(users)  # everyone seated exactly once
        per_match = (await s.execute(
            select(MagnateSeat.match_id, func.count()).where(MagnateSeat.match_id.in_({r.match_id for r in rows}))
            .group_by(MagnateSeat.match_id)
        )).all()
        assert all(count <= 4 for _, count in per_match)


async def test_concurrent_bot_match_creation_starts_only_one(pg):
    uid = await _user(pg)
    results = await asyncio.gather(*[_as(pg, uid, magnate_service.create_bot_match) for _ in range(4)])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        user = await s.get(User, uid)
        assert user.magnate_hourly_attempts == 1


async def test_parallel_actions_with_one_version_apply_once(pg):
    uid = await _user(pg)
    match = await _as(pg, uid, magnate_service.create_bot_match)
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: magnate_service.act(s, u, match.id, "roll", None, match.version)) for _ in range(5)
    ])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        row = await s.get(MagnateMatch, match.id)
        assert row.version == match.version + 1 and row.server_state["roll_n"] >= 1


async def test_sweep_and_reads_process_an_expired_turn_once(pg):
    uid = await _user(pg)
    match = await _as(pg, uid, magnate_service.create_bot_match)
    async with pg() as s:
        row = await s.get(MagnateMatch, match.id)
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        state = copy.deepcopy(row.server_state)
        state["deadline"] = past.isoformat()
        row.server_state = state
        flag_modified(row, "server_state")
        row.next_deadline_at = past
        await s.commit()

    async def sweep(s, _user):
        return await magnate_service.sweep_due(s)

    await asyncio.gather(
        _as(pg, uid, sweep), _as(pg, uid, sweep),
        _as(pg, uid, lambda s, u: magnate_service.get_match(s, u, match.id)),
        _as(pg, uid, lambda s, u: magnate_service.get_match(s, u, match.id)),
    )
    async with pg() as s:
        row = await s.get(MagnateMatch, match.id)
        assert row.server_state["players"][0]["missed"] == 1
