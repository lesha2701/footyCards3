import os

# Captured before the SQLite override below: the real-Postgres tests derive their
# own `<db>_test` database from it (see tests/real_postgres.py).
_APP_DATABASE_URL = os.environ.get("DATABASE_URL")

os.environ["TELEGRAM_BOT_TOKEN"] = "TEST:BOT_TOKEN_FOR_UNIT_TESTS"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["DEV_MODE"] = "true"
os.environ["DEV_USER_TELEGRAM_ID"] = "999000001"
os.environ["ADMIN_TELEGRAM_IDS"] = "999000001,5095749754"
os.environ["JWT_SECRET"] = "test_only_secret"
os.environ["STARTING_BALANCE"] = "500"
os.environ["ENVIRONMENT"] = "test"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401 - ensures all tables are registered on Base.metadata
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from tests import real_postgres

settings = get_settings()

engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture(autouse=True)
async def _fresh_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def trade_guards_off(_fresh_schema):
    """Turns off the trade anti-farming rules (new-account give ban, daily
    coin cap, tax) for tests about other trade behavior: their freshly
    registered users would otherwise be too young to give anything."""
    from app.services.game_config_service import get_config

    async with TestSessionLocal() as session:
        config = await get_config(session)
        config.trade_send_min_account_age_days = 0
        config.trade_send_min_active_days = 0
        config.trade_daily_coins_receive_cap = 0
        config.trade_coin_tax_pct = 0
        config.trade_coins_enabled = True
        config.trade_cards_both_sides = False
        await session.commit()


@pytest_asyncio.fixture
async def stake_guards_off(_fresh_schema):
    """Turns off the stake anti-farming rules (max stake, new-account ban,
    pair and daily-profit limits) for tests about other stake behavior."""
    from app.services.game_config_service import get_config

    async with TestSessionLocal() as session:
        config = await get_config(session)
        config.stake_max_coins = 10_000_000
        config.stake_pair_daily_limit = 0
        config.stake_daily_profit_cap = 0
        config.trade_send_min_account_age_days = 0
        config.trade_send_min_active_days = 0
        await session.commit()


@pytest.fixture
def bot_token() -> str:
    return settings.telegram_bot_token


@pytest.fixture(scope="session")
def real_pg_url() -> str:
    """URL of the dedicated `*_test` Postgres database, created and migrated on
    first use; skips when the server is unreachable (see tests/real_postgres.py)."""
    url = real_postgres.resolve_url(_APP_DATABASE_URL)
    real_postgres.prepare_database(url)
    return url


@pytest_asyncio.fixture
async def real_pg(real_pg_url):
    """async_sessionmaker bound to the real-Postgres test database. Every row the
    test (or the code under test) creates is deleted on teardown, pass or fail."""
    tracker = real_postgres.RealPostgres(real_pg_url)
    try:
        await tracker.start()
        # lock_timeout: a test that leaves a transaction holding a row lock fails
        # instead of hanging the whole run on the racer waiting for that lock.
        engine = create_async_engine(
            real_pg_url, pool_size=20, pool_pre_ping=True, connect_args={"server_settings": {"lock_timeout": "30s"}}
        )
        try:
            yield async_sessionmaker(bind=engine, expire_on_commit=False)
        finally:
            await engine.dispose()
    finally:
        await tracker.finish()
