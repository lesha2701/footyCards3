from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# pool_size/max_overflow/pool_timeout are QueuePool-specific — SQLite (used
# by the test suite, see tests/conftest.py) gets StaticPool instead and
# rejects these kwargs outright. Only apply them for the real Postgres
# engine, which is the only one that actually needs sizing beyond
# SQLAlchemy's small defaults (see config.py's db_pool_size comment).
_pool_kwargs = (
    {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_timeout": settings.db_pool_timeout,
        "pool_recycle": settings.db_pool_recycle,
    }
    if not settings.database_url.startswith("sqlite")
    else {}
)

engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True, **_pool_kwargs)
AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
