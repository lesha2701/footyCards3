"""Card-skill concurrency against a REAL PostgreSQL (row locks, unique
indexes). SQLite ignores SELECT ... FOR UPDATE, so these only run when
CARD_SKILLS_PG_URL points at a database already migrated to head, e.g.:

    CARD_SKILLS_PG_URL=postgresql+asyncpg://postgres:pw@localhost:5499/mig_clean \
        pytest tests/test_card_skills_postgres.py -v

Each test uses its own fresh users/cards, so the database can be reused.
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.card_skill import CardSkillLedger, UserSkillToken
from app.models.enums import CardSource, Position, Rarity, TaskCategory, TaskConditionType
from app.models.player import Player
from app.models.task import TaskDefinition, UserTask
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.card_skill import SkillOperationRequest
from app.schemas.trade import TradeCreateRequest
from app.services import card_skill_service, task_service, trade_service
from app.services.wallet_service import lock_user_for_update

PG_URL = os.environ.get("CARD_SKILLS_PG_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="CARD_SKILLS_PG_URL not set (needs real PostgreSQL)")


@pytest.fixture(autouse=True)
def _fresh_schema():
    # Overrides conftest's SQLite create_all/drop_all: the PG database is
    # migrated by alembic and must not be dropped.
    yield


@pytest.fixture
async def pg():
    engine = create_async_engine(PG_URL, pool_size=10)
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()


async def _user(pg, balance=0) -> int:
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="PG", balance=balance)
        s.add(user)
        await s.commit()
        return user.id


async def _card(pg, owner_id: int, position=Position.ST, **kw) -> int:
    async with pg() as s:
        player = Player(
            first_name="P", last_name="G", display_name=f"PG {uuid.uuid4().hex[:6]}", rating=75,
            rarity=Rarity.common, country="X", club="Y", position=position,
        )
        s.add(player)
        await s.flush()
        card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed, serial_number=1, **kw)
        s.add(card)
        await s.commit()
        return card.id


async def _grant(pg, user_id: int, code: str, qty: int):
    async with pg() as s:
        locked = await lock_user_for_update(s, user_id)
        await card_skill_service.grant_tokens(s, locked, code, qty, "grant_admin", reason="pg-test")
        await s.commit()


async def _tokens(pg, user_id: int, code: str) -> int:
    async with pg() as s:
        row = (await s.execute(
            select(UserSkillToken).where(UserSkillToken.user_id == user_id, UserSkillToken.skill_code == code)
        )).scalar_one_or_none()
        return row.quantity if row else 0


async def _op(pg, user_id: int, card_id: int, request: SkillOperationRequest, key: str | None = None):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await card_skill_service.perform_operation(s, user, card_id, request, key or str(uuid.uuid4()))
        except AppError as exc:
            await s.rollback()
            return exc


def _assign(code="sniper"):
    return SkillOperationRequest(
        operation="assign", skill_code=code, expected_skill_code=None, expected_level=None,
        expected_token_cost=1, expected_coin_cost=0,
    )


def _upgrade(code="sniper"):
    return SkillOperationRequest(
        operation="upgrade", expected_skill_code=code, expected_level=1, expected_token_cost=2, expected_coin_cost=400,
    )


async def test_two_concurrent_assigns_on_one_card_charge_once(pg):
    user_id = await _user(pg)
    card_id = await _card(pg, user_id)
    await _grant(pg, user_id, "sniper", 2)
    await _grant(pg, user_id, "dribbler", 1)

    results = await asyncio.gather(
        _op(pg, user_id, card_id, _assign("sniper")), _op(pg, user_id, card_id, _assign("dribbler")),
    )
    ok = [r for r in results if not isinstance(r, AppError)]
    failed = [r for r in results if isinstance(r, AppError)]
    assert len(ok) == 1 and len(failed) == 1
    assert failed[0].details["reason"] in ("stale_state", "already_has_skill")

    async with pg() as s:
        card = await s.get(UserCard, card_id)
        assert (card.skill_code, card.skill_level) == (ok[0].skill_code, 1)
    spent = (2 - await _tokens(pg, user_id, "sniper")) + (1 - await _tokens(pg, user_id, "dribbler"))
    assert spent == 1


async def test_same_idempotency_key_raced_twice_charges_once(pg):
    user_id = await _user(pg)
    card_id = await _card(pg, user_id)
    await _grant(pg, user_id, "sniper", 3)
    key = str(uuid.uuid4())
    results = await asyncio.gather(*[_op(pg, user_id, card_id, _assign(), key) for _ in range(3)])
    assert sum(1 for r in results if not isinstance(r, AppError) and not r.replayed) == 1
    assert await _tokens(pg, user_id, "sniper") == 2
    async with pg() as s:
        count = (await s.execute(
            select(func.count(CardSkillLedger.id)).where(CardSkillLedger.idempotency_key == key)
        )).scalar_one()
        assert count == 1


async def test_two_upgrades_with_balance_for_only_one(pg):
    user_id = await _user(pg, balance=500)
    card_a = await _card(pg, user_id, skill_code="sniper", skill_level=1)
    card_b = await _card(pg, user_id, skill_code="sniper", skill_level=1)
    await _grant(pg, user_id, "sniper", 4)

    results = await asyncio.gather(_op(pg, user_id, card_a, _upgrade()), _op(pg, user_id, card_b, _upgrade()))
    ok = [r for r in results if not isinstance(r, AppError)]
    failed = [r for r in results if isinstance(r, AppError)]
    assert len(ok) == 1 and len(failed) == 1
    assert failed[0].code == "insufficient_balance"
    async with pg() as s:
        user = await s.get(User, user_id)
        assert user.balance == 100
        levels = sorted([(await s.get(UserCard, cid)).skill_level for cid in (card_a, card_b)])
        assert levels == [1, 2]
    assert await _tokens(pg, user_id, "sniper") == 2


async def test_assign_racing_a_trade_offer_never_loses_tokens(pg):
    sender_id = await _user(pg)
    receiver_id = await _user(pg)
    async with pg() as s:
        receiver = await s.get(User, receiver_id)
        receiver.accept_trades = True
        await s.commit()
    card_id = await _card(pg, sender_id)
    await _grant(pg, sender_id, "sniper", 1)

    async def offer():
        async with pg() as s:
            sender = await s.get(User, sender_id)
            try:
                return await trade_service.create_offer(
                    s, sender, TradeCreateRequest(receiver_id=receiver_id, offered_card_ids=[card_id], requested_card_ids=[]),
                )
            except AppError as exc:
                await s.rollback()
                return exc

    assign_result, offer_result = await asyncio.gather(_op(pg, sender_id, card_id, _assign()), offer())
    assert not isinstance(offer_result, AppError)

    async with pg() as s:
        card = await s.get(UserCard, card_id)
        skilled = card.skill_code == "sniper"
    # Exactly one consistent outcome: either the skill landed (token spent)
    # before the offer locked the card, or the assign was refused (token kept).
    if skilled:
        assert not isinstance(assign_result, AppError)
        assert await _tokens(pg, sender_id, "sniper") == 0
        assert offer_result.offered_cards[0].skill_code == "sniper"
    else:
        assert isinstance(assign_result, AppError) and assign_result.details["reason"] == "card_locked"
        assert await _tokens(pg, sender_id, "sniper") == 1

    async with pg() as s:
        receiver = await s.get(User, receiver_id)
        await trade_service.accept_offer(s, receiver, offer_result.id)
    async with pg() as s:
        card = await s.get(UserCard, card_id)
        assert card.owner_id == receiver_id
        assert (card.skill_code == "sniper") == skilled
        offer_row = await s.get(TradeOffer, offer_result.id)
        assert offer_row.status.value == "accepted"


async def test_concurrent_task_claims_grant_tokens_once(pg):
    user_id = await _user(pg)
    async with pg() as s:
        definition = TaskDefinition(
            code=f"pg_skill_{uuid.uuid4().hex[:8]}", name="PG", description="", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=1, reward_coins=10,
            reward_skill_code="reflexes", reward_skill_tokens=3, is_active=False,
        )
        s.add(definition)
        await s.flush()
        user_task = UserTask(
            user_id=user_id, task_definition_id=definition.id, progress=1, completed_at=datetime.now(timezone.utc),
        )
        s.add(user_task)
        await s.commit()
        task_id = user_task.id

    async def claim():
        async with pg() as s:
            user = await s.get(User, user_id)
            try:
                return await task_service.claim_task_reward(s, user, task_id)
            except AppError as exc:
                await s.rollback()
                return exc

    results = await asyncio.gather(*[claim() for _ in range(4)])
    assert sum(1 for r in results if not isinstance(r, AppError)) == 1
    assert await _tokens(pg, user_id, "reflexes") == 3


async def test_concurrent_admin_grants_with_one_key_grant_once(pg):
    user_id = await _user(pg)
    key = f"admin-{uuid.uuid4()}"

    async def grant():
        async with pg() as s:
            locked = await lock_user_for_update(s, user_id)
            try:
                await card_skill_service.grant_tokens(
                    s, locked, "playmaker", 5, "grant_admin", reason="race", idempotency_key=key,
                )
                await s.commit()
            except Exception:  # noqa: BLE001 - the unique-index loser
                await s.rollback()

    await asyncio.gather(*[grant() for _ in range(4)])
    assert await _tokens(pg, user_id, "playmaker") == 5
