"""«21» concurrency against a REAL PostgreSQL (row locks, partial unique
index). SQLite ignores SELECT ... FOR UPDATE, so these run on the `real_pg` fixture
(tests/conftest.py): a dedicated `*_test` database, created and migrated to head
on first use, never the app's own; every row a test creates is deleted on
teardown. See CLAUDE.md → Backend checks.
Migration 0136 seeds the golden/jackpot pools these rely on.
"""
import asyncio
import secrets
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.blackjack import BlackjackMatch
from app.models.enums import Position, Rarity
from app.models.game_config import GameConfig
from app.models.pack import StarsInvoice
from app.models.player import Player
from app.models.user import User
from app.models.wheel import WheelSpin
from app.services import blackjack_engine as engine
from app.services import blackjack_service, stars_payment_service

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
        # The seeded golden/jackpot pools include card prizes, which need at
        # least one droppable player to grant (pick_random_player).
        if (await s.execute(select(Player.id).limit(1))).first() is None:
            s.add(Player(
                first_name="B", last_name="J", display_name="B J", rating=80, rarity=Rarity.legendary,
                country="X", club="Y", position=Position.ST, quick_sell_price=400, is_active=True,
            ))
            await s.commit()
    yield real_pg


async def _new_user(pg, **fields) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="BJ", balance=0, **fields)
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


def _stack(monkeypatch, player, dealer):
    deck = [player[0], dealer[0], player[1], dealer[1]]
    deck += [c for c in engine.full_deck() if c not in deck]
    monkeypatch.setattr(blackjack_service, "_shuffled_deck", lambda: list(deck))


async def test_concurrent_starts_create_one_match_and_consume_one_entry(pg, monkeypatch):
    user_id = await _new_user(pg, blackjack_paid_entries=5)
    _stack(monkeypatch, ["fw:10", "mf:4"], ["gk:9", "df:8"])

    results = await asyncio.gather(*[_as(pg, user_id, blackjack_service.start_match) for _ in range(6)])
    ids = {r.match.id for r in results if not isinstance(r, AppError)}
    assert len(ids) == 1

    async with pg() as s:
        count = (await s.execute(
            select(func.count(BlackjackMatch.id)).where(BlackjackMatch.user_id == user_id)
        )).scalar()
        user = await s.get(User, user_id)
        assert count == 1
        assert user.blackjack_free_used_today == 1 and user.blackjack_paid_entries == 5


async def test_concurrent_stands_pay_out_once(pg, monkeypatch):
    user_id = await _new_user(pg)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:10", "df:7"])  # stand = win → golden spin
    started = await _as(pg, user_id, blackjack_service.start_match)
    match_id = started.match.id

    results = await asyncio.gather(*[
        _as(pg, user_id, lambda s, u: blackjack_service.stand(s, u, match_id)) for _ in range(6)
    ])
    assert all(not isinstance(r, AppError) for r in results)
    assert sum(1 for r in results if r.spin_result is not None) == 1

    async with pg() as s:
        spins = (await s.execute(select(WheelSpin).where(WheelSpin.blackjack_match_id == match_id))).scalars().all()
        assert len(spins) == 1


async def test_concurrent_stars_deliveries_bank_one_entry(pg):
    user_id = await _new_user(pg)
    token = secrets.token_urlsafe(16)
    async with pg() as s:
        user = await s.get(User, user_id)
        s.add(StarsInvoice(user_id=user_id, is_blackjack_entry=True, payload_token=token, stars_amount=10))
        await s.commit()
        telegram_id = user.telegram_id

    charge = f"bj-pg-{uuid.uuid4().hex}"

    async def deliver():
        async with pg() as s:
            try:
                return await stars_payment_service.deliver_payment(s, token, telegram_id, charge, 10)
            except Exception as exc:  # noqa: BLE001 — a losing racer may surface the unique violation
                return exc

    await asyncio.gather(*[deliver() for _ in range(5)])
    async with pg() as s:
        user = await s.get(User, user_id)
        assert user.blackjack_paid_entries == 1 and user.blackjack_paid_bought_today == 1
