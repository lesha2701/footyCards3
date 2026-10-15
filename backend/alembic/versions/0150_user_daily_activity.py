"""user_daily_activity: per-user, per-day activity history for admin analytics

Revision ID: 0150
Revises: 0149
Create Date: 2026-10-16

`users.last_seen_at` only keeps the latest visit, so retention (D1/D7/D30),
DAU history and the new-player funnel can't be computed from it. From now
on core/dependencies.py writes one row per user per local day. The past is
backfilled from every timestamped per-user activity the database already
records (registration, last visit, coin transactions, pack openings, games,
Stars payments) — a lower bound of real activity, never an invented one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0150"
down_revision: Union[str, None] = "0149"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, user column, timestamp column) — each is used only if it exists,
# so the backfill doesn't depend on every feature table being present.
_BACKFILL_SOURCES = [
    ("users", "id", "created_at"),
    ("users", "id", "last_seen_at"),
    ("coin_transactions", "user_id", "created_at"),
    ("pack_openings", "user_id", "created_at"),
    ("matches", "user_id", "created_at"),
    ("game_sessions", "user_id", "created_at"),
    ("tactico_matches", "user_id", "created_at"),
    ("tactico_matches", "opponent_user_id", "created_at"),
    ("stratego_matches", "user_id", "created_at"),
    ("stratego_matches", "opponent_user_id", "created_at"),
    ("penalty_matches", "user_id", "created_at"),
    ("penalty_matches", "opponent_user_id", "created_at"),
    ("blackjack_matches", "user_id", "created_at"),
    ("magnate_seats", "user_id", "joined_at"),
    ("wheel_spins", "user_id", "created_at"),
    ("stars_invoices", "user_id", "completed_at"),
    ("daily_rewards", "user_id", "created_at"),
]


def _timezone() -> str:
    try:
        from app.config import get_settings

        return get_settings().timezone
    except Exception:  # pragma: no cover - settings unavailable in some envs
        return "Europe/Moscow"


def upgrade() -> None:
    op.create_table(
        "user_daily_activity",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "day"),
    )
    op.create_index("ix_user_daily_activity_day", "user_daily_activity", ["day"])

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    existing = {t: {c["name"] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    tz = _timezone()
    for table, user_col, ts_col in _BACKFILL_SOURCES:
        cols = existing.get(table)
        if not cols or user_col not in cols or ts_col not in cols:
            continue
        bind.execute(
            sa.text(
                f"""
                INSERT INTO user_daily_activity (user_id, day)
                SELECT DISTINCT s.{user_col}, (s.{ts_col} AT TIME ZONE :tz)::date
                FROM {table} s
                JOIN users u ON u.id = s.{user_col}
                WHERE s.{user_col} IS NOT NULL AND s.{ts_col} IS NOT NULL
                ON CONFLICT DO NOTHING
                """
            ),
            {"tz": tz},
        )


def downgrade() -> None:
    op.drop_index("ix_user_daily_activity_day", table_name="user_daily_activity")
    op.drop_table("user_daily_activity")
