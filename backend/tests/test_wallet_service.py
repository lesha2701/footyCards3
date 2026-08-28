import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.enums import TransactionType
from app.models.user import User
from app.services import wallet_service

# The `ck_coin_tx_balance_non_negative` CHECK constraint (migrations 0055/0076) is a real
# Postgres constraint applied only via Alembic — it is NOT part of the SQLAlchemy model
# metadata, so tests/conftest.py's SQLite `Base.metadata.create_all` never creates it and
# the in-memory suite can't catch a regression here. Same "verify manually against real
# Postgres" approach as test_club_packs.py's REAL_POSTGRES_URL tests — written as a
# permanent, self-cleaning regression test rather than a one-off manual check.
REAL_POSTGRES_URL = os.environ.get("REAL_POSTGRES_URL", "postgresql+asyncpg://postgres:1234@postgres:5432/footycards")


async def test_credit_coins_succeeds_while_balance_negative_from_clawback():
    """Reproduces the production bug: a player clawed back into negative balance by the
    premium-task subscription sweep (bot/db.py's adjust_coins_allow_negative, which uses the
    exempted `premium_subscription_adjustment` type) could not earn ANY coins afterwards —
    every game/task/daily reward 500'd with a CheckViolationError, since balance_after stayed
    negative until the balance crossed back to zero on its own. Fixed by 0076, which also
    allows any transaction with amount >= 0 (a credit can never make the balance worse)."""
    engine = create_async_engine(REAL_POSTGRES_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OSError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")
    except OperationalError as exc:
        await engine.dispose()
        pytest.skip(f"real dev Postgres not reachable at {REAL_POSTGRES_URL!r}: {exc!r}")

    RealSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    suffix = uuid.uuid4().hex[:10]

    setup = RealSessionLocal()
    user_id = None
    try:
        user = User(telegram_id=991_000_000_000 + uuid.uuid4().int % 1_000_000_000, username=f"wallet_{suffix}", balance=0)
        setup.add(user)
        await setup.flush()
        user_id = user.id

        # Mirrors bot/db.py's adjust_coins_allow_negative raw INSERT for the clawback itself.
        await setup.execute(
            text(
                "INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, created_at) "
                "VALUES (:uid, -3912, 0, -3912, 'premium_subscription_adjustment', 'test clawback', now())"
            ),
            {"uid": user_id},
        )
        user.balance = -3912
        setup.add(user)
        await setup.commit()

        session = RealSessionLocal()
        try:
            locked_user = await wallet_service.lock_user_for_update(session, user_id)
            assert locked_user.balance == -3912
            await wallet_service.credit_coins(session, locked_user, 20, TransactionType.game_reward, "test reward")
            await session.commit()
            assert locked_user.balance == -3892
        finally:
            await session.close()
    finally:
        if user_id is not None:
            cleanup = RealSessionLocal()
            await cleanup.execute(text("DELETE FROM coin_transactions WHERE user_id = :uid"), {"uid": user_id})
            await cleanup.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
            await cleanup.commit()
            await cleanup.close()
        await setup.close()
        await engine.dispose()
