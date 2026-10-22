"""«Мордобой» concurrency against a REAL PostgreSQL (row locks). SQLite
ignores SELECT ... FOR UPDATE, so these run on the `real_pg` fixture
(tests/conftest.py) — see CLAUDE.md → Backend checks.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.enums import CardSource, MordoboiMatchStatus, Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.mordoboi import MordoboiMatch
from app.models.player import Player
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import mordoboi_service


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
        config.mordoboi_enabled = True
        config.mordoboi_rounds = 1
        config.mordoboi_exchanges_per_round = 2
        await s.commit()
    yield real_pg


async def _boxer(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=0)
        s.add(user)
        await s.flush()
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="B", last_name=tag, display_name=f"B {tag}", rating=80, rarity=Rarity.rare,
            country="X", club="Y", position=Position.ST, quick_sell_price=1, is_active=True,
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


async def _friend_bout(pg):
    a, b = await _boxer(pg), await _boxer(pg)
    created = await _as(pg, a, lambda s, u: mordoboi_service.create_challenge(s, u, b))
    match = await _as(pg, b, lambda s, u: mordoboi_service.accept_challenge(s, u, created.id))
    return a, b, match


async def test_concurrent_bot_bout_creation_starts_only_one(pg):
    uid = await _boxer(pg)
    results = await asyncio.gather(*[_as(pg, uid, mordoboi_service.create_bot_match) for _ in range(4)])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        active = (await s.execute(
            select(func.count()).select_from(MordoboiMatch)
            .where(MordoboiMatch.user_id == uid, MordoboiMatch.status == MordoboiMatchStatus.in_progress)
        )).scalar_one()
        user = await s.get(User, uid)
        assert active == 1 and user.mordoboi_hourly_attempts == 1


async def test_both_sides_pick_at_once_resolve_exactly_once(pg):
    a, b, match = await _friend_bout(pg)
    results = await asyncio.gather(
        _as(pg, a, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "hook", match.version)),
        _as(pg, b, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "jab", match.version)),
    )
    assert not any(isinstance(r, AppError) for r in results)
    async with pg() as s:
        m = await s.get(MordoboiMatch, match.id)
        assert len(m.server_state["log"]) == 1 and m.version == match.version + 1
        assert m.server_state["log"][0]["actions"] == {"user": "hook", "opponent": "jab"}


async def test_same_pick_sent_twice_at_once_counts_once(pg):
    uid = await _boxer(pg)
    match = await _as(pg, uid, mordoboi_service.create_bot_match)
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "block", match.version)) for _ in range(3)
    ])
    assert not any(isinstance(r, AppError) for r in results)  # retries are no-ops, not errors
    async with pg() as s:
        m = await s.get(MordoboiMatch, match.id)
        assert len(m.server_state["log"]) == 1


async def test_last_exchange_raced_by_both_sides_pays_each_once(pg):
    a, b, match = await _friend_bout(pg)
    await _as(pg, a, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "block", match.version))
    await _as(pg, b, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "block", match.version))
    v = match.version + 1
    await asyncio.gather(
        _as(pg, a, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "block", v)),
        _as(pg, b, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "block", v)),
        _as(pg, a, lambda s, u: mordoboi_service.forfeit_match(s, u, match.id)),
    )
    async with pg() as s:
        m = await s.get(MordoboiMatch, match.id)
        assert m.status == MordoboiMatchStatus.finished
        txs = (await s.execute(
            select(CoinTransaction).where(
                CoinTransaction.type == TransactionType.mordoboi_reward,
                or_(CoinTransaction.user_id == a, CoinTransaction.user_id == b),
            )
        )).scalars().all()
        assert len({t.user_id for t in txs}) == len(txs) <= 2


async def test_sweep_and_pick_racing_on_a_missed_deadline(pg):
    a, b, match = await _friend_bout(pg)
    async with pg() as s:
        m = await s.get(MordoboiMatch, match.id)
        state = dict(m.server_state)
        state["deadline"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        m.server_state = state
        flag_modified(m, "server_state")
        await s.commit()
    await asyncio.gather(
        _as(pg, a, lambda s, u: mordoboi_service.get_match(s, u, match.id)),
        _as(pg, b, lambda s, u: mordoboi_service.list_matches(s, u)),
        _as(pg, a, lambda s, u: mordoboi_service.submit_pick(s, u, match.id, "jab", match.version)),
    )
    async with pg() as s:
        m = await s.get(MordoboiMatch, match.id)
        # Exactly one exchange was played, whoever got the lock first.
        assert len(m.server_state["log"]) == 1
