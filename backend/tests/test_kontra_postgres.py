"""«Контратака» concurrency against a REAL PostgreSQL (row locks) — see
CLAUDE.md → Backend checks."""
import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.game_config import GameConfig
from app.models.kontra import KontraBattle
from app.models.player import Player
from app.models.user import User
from app.services import kontra_service


@pytest.fixture(autouse=True)
def _fresh_schema():
    yield


@pytest.fixture
async def pg(real_pg):
    async with real_pg() as s:
        config = await s.get(GameConfig, 1)
        if config is None:
            config = GameConfig(id=1)
            s.add(config)
        config.kontra_enabled = True
        config.kontra_boss_daily_attempts = 3
        config.kontra_boss_max_rounds = 4
        await s.commit()
    yield real_pg


async def _fighter(pg) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=0)
        s.add(user)
        await s.flush()
        for i, pos in enumerate((Position.ST, Position.RW, Position.CM, Position.CB, Position.GK)):
            tag = uuid.uuid4().hex[:6]
            player = Player(first_name="K", last_name=tag, display_name=f"K {tag}", rating=80 - i, rarity=Rarity.epic,
                            country="X", club="Y", position=pos, quick_sell_price=1, is_active=True)
            s.add(player)
            await s.flush()
            s.add(UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed))
        await s.commit()
        return user.id


async def _as(pg, user_id, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def test_parallel_boss_starts_open_one_battle_and_spend_one_attempt(pg):
    uid = await _fighter(pg)
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: kontra_service.start_boss(s, u, manual=True)) for _ in range(4)
    ])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    async with pg() as s:
        user = await s.get(User, uid)
        battles = (await s.execute(select(func.count()).select_from(KontraBattle).where(KontraBattle.user_id == uid))).scalar_one()
        assert battles == 1 and user.kontra_boss_attempts_today == 1


async def test_same_action_sent_twice_at_once_is_applied_once(pg):
    uid = await _fighter(pg)
    battle = await _as(pg, uid, lambda s, u: kontra_service.start_boss(s, u, manual=True))
    assert not isinstance(battle, AppError) and battle.can_act
    results = await asyncio.gather(*[
        _as(pg, uid, lambda s, u: kontra_service.act(s, u, battle.id, battle.version, battle.turn_of, "strike", None))
        for _ in range(3)
    ])
    assert not any(isinstance(r, AppError) for r in results)
    async with pg() as s:
        stored = await s.get(KontraBattle, battle.id)
        abilities = [e for e in stored.server_state["events"] if e["kind"] == "ability" and e["actor"] == battle.turn_of]
        assert len(abilities) == 1
