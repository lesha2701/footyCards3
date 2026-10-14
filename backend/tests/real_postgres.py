"""Harness for the tests that need a REAL PostgreSQL (SELECT ... FOR UPDATE,
SKIP LOCKED, unique-constraint races) — SQLite ignores all of that.

Isolation: these tests never touch the application's database. The target URL is
`REAL_POSTGRES_URL` if set, otherwise the app's own DATABASE_URL (as the process
started with it, before tests/conftest.py swaps it for SQLite) with `_test`
appended to the database name, otherwise DEFAULT_URL. The database name MUST end
with `_test` — anything else fails the test instead of writing into live data.
A missing test database is created on the same server and migrated to head
(`alembic upgrade head`) once per pytest session.

Cleanup: every test snapshots, per table, the highest integer primary key (or
the full key set for the couple of tables without one) and on teardown — pass
or fail, however far setup got — deletes every row created after the snapshot,
children before parents. That covers rows the code under test created too
(tournaments, transactions, openings, user_cards, ...), not only the test's own
fixtures. Pre-existing rows the test repointed at a new row (through any FK) get their
snapshot value back first.
"""
import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import Integer, delete, func, select, text, tuple_, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from sqlalchemy.pool import NullPool

from app import models  # noqa: F401 - registers every table on Base.metadata
from app.database import Base

DEFAULT_URL = "postgresql+asyncpg://postgres:1234@postgres:5432/footycards_test"
TEST_DB_SUFFIX = "_test"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def resolve_url(app_database_url: str | None) -> str:
    explicit = os.environ.get("REAL_POSTGRES_URL")
    if explicit:
        return explicit
    if app_database_url and app_database_url.startswith("postgresql"):
        url = make_url(app_database_url)
        if url.database and not url.database.endswith(TEST_DB_SUFFIX):
            url = url.set(database=f"{url.database}{TEST_DB_SUFFIX}")
        return url.render_as_string(hide_password=False)
    return DEFAULT_URL


def _safe(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


def prepare_database(url: str) -> None:
    """Guard + create-if-missing + migrate. Skips when the server is unreachable."""
    database = make_url(url).database or ""
    if not database.endswith(TEST_DB_SUFFIX):
        pytest.fail(
            f"Refusing to run real-Postgres tests against {_safe(url)}: the database name must end with "
            f"{TEST_DB_SUFFIX!r} — these tests create and delete rows and must never run against app data.",
            pytrace=False,
        )
    try:
        asyncio.run(_create_database_if_missing(url))
    except (OSError, DBAPIError) as exc:
        pytest.skip(f"real Postgres not reachable at {_safe(url)}: {exc!r}")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed for {_safe(url)}:\n{result.stdout}\n{result.stderr}", pytrace=False)


async def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_async_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            exists = (
                await conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database})
            ).first()
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await admin.dispose()


def _int_pk(table):
    pk = list(table.primary_key.columns)
    if len(pk) == 1 and isinstance(pk[0].type, Integer):
        return pk[0]
    return None


@dataclass
class Snapshot:
    max_ids: dict[str, int] = field(default_factory=dict)
    keys: dict[str, set[tuple]] = field(default_factory=dict)
    # table -> {pk: {fk column: value}} for pre-existing rows, to undo repointing.
    fk_values: dict[str, dict[int, dict[str, object]]] = field(default_factory=dict)


async def take_snapshot(conn: AsyncConnection) -> Snapshot:
    snapshot = Snapshot()
    for table in Base.metadata.sorted_tables:
        pk = _int_pk(table)
        if pk is not None:
            snapshot.max_ids[table.name] = (await conn.execute(select(func.coalesce(func.max(pk), 0)))).scalar_one()
            fk_columns = sorted({fk.parent for fk in table.foreign_keys if fk.parent is not pk}, key=lambda c: c.name)
            if fk_columns:
                rows = await conn.execute(select(pk, *fk_columns))
                snapshot.fk_values[table.name] = {
                    row[0]: {col.name: value for col, value in zip(fk_columns, row[1:])} for row in rows
                }
        else:
            snapshot.keys[table.name] = {tuple(row) for row in await conn.execute(select(*table.primary_key.columns))}
    return snapshot


def _new_rows(table, snapshot: Snapshot):
    """WHERE clause selecting the rows of `table` created after the snapshot."""
    pk = _int_pk(table)
    if pk is not None:
        return pk > snapshot.max_ids[table.name]
    known = snapshot.keys[table.name]
    columns = list(table.primary_key.columns)
    if not known:
        return columns[0].is_not(None)
    if len(columns) == 1:
        return columns[0].not_in([k[0] for k in known])
    return tuple_(*columns).not_in([tuple(k) for k in known])


async def delete_created_rows(conn: AsyncConnection, snapshot: Snapshot) -> None:
    await conn.execute(text("SET LOCAL lock_timeout = '15s'"))
    tables = Base.metadata.sorted_tables

    # Pre-existing rows must survive: the code under test may have repointed them at rows
    # about to go (e.g. the tournament_queue_state singleton's current_queue_id) — restore
    # the value they had at snapshot time.
    for table in tables:
        pk = _int_pk(table)
        before = snapshot.fk_values.get(table.name)
        if pk is None or before is None:
            continue
        for fk in table.foreign_keys:
            doomed = select(fk.column).where(_new_rows(fk.column.table, snapshot))
            repointed = await conn.execute(
                select(pk).where(pk <= snapshot.max_ids[table.name], fk.parent.in_(doomed))
            )
            for (row_id,) in repointed:
                if row_id in before:
                    await conn.execute(
                        update(table).where(pk == row_id).values({fk.parent.name: before[row_id][fk.parent.name]})
                    )

    for table in reversed(tables):
        await conn.execute(delete(table).where(_new_rows(table, snapshot)))


class RealPostgres:
    """Per-test handle: snapshot on enter, delete everything created on exit."""

    def __init__(self, url: str):
        self._maintenance = create_async_engine(url, poolclass=NullPool)
        self._snapshot: Snapshot | None = None

    async def start(self) -> None:
        async with self._maintenance.connect() as conn:
            self._snapshot = await take_snapshot(conn)

    async def finish(self) -> None:
        try:
            if self._snapshot is not None:
                async with self._maintenance.begin() as conn:
                    await delete_created_rows(conn, self._snapshot)
        finally:
            await self._maintenance.dispose()
