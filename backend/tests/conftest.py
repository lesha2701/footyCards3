import os

os.environ["TELEGRAM_BOT_TOKEN"] = "TEST:BOT_TOKEN_FOR_UNIT_TESTS"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["DEV_MODE"] = "true"
os.environ["DEV_USER_TELEGRAM_ID"] = "999000001"
os.environ["ADMIN_TELEGRAM_IDS"] = "999000001"
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


@pytest.fixture
def bot_token() -> str:
    return settings.telegram_bot_token
