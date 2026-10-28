"""«Штрафной 3D»: paid refills of the hourly series — the day's first for
coins, the rest for Telegram Stars, a daily cap; per-user counters and the
banked series a start spends once the hourly cap is reached.

Revision ID: 0213
Revises: 0212
Create Date: 2026-10-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0213"
down_revision: Union[str, None] = "0212"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG = {
    "free_kick_refill_daily_limit": 5,
    "free_kick_refill_coins": 200,
    "free_kick_refill_stars": 2,
}


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'free_kick_refill'")
    for name, default in CONFIG.items():
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=str(default)))
    op.add_column("users", sa.Column("free_kick_refills_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("free_kick_refills_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("free_kick_bonus_series", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "free_kick_bonus_series")
    op.drop_column("users", "free_kick_refills_reset_at")
    op.drop_column("users", "free_kick_refills_today")
    for name in reversed(list(CONFIG)):
        op.drop_column("game_config", name)
    # A value can't be dropped from a Postgres enum; it stays, unused.
