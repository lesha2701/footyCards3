"""«Атака 1 на 1»: the game type, users' hourly/daily counters and the
GameConfig settings (attacks per series, daily cap, coins and bonuses).

Revision ID: 0247
Revises: 0246
Create Date: 2026-11-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0247"
down_revision: Union[str, None] = "0246"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("one_on_one_attacks", "5"),
    ("one_on_one_daily_limit", "8"),
    ("one_on_one_goal_coins", "20"),
    ("one_on_one_feint_bonus", "10"),
    ("one_on_one_chip_bonus", "15"),
    ("one_on_one_near_coins", "3"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'one_on_one'")
    op.add_column("users", sa.Column("one_on_one_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("one_on_one_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("one_on_one_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("one_on_one_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    for name in (
        "one_on_one_hour_started_at", "one_on_one_hourly_attempts",
        "one_on_one_attempts_reset_at", "one_on_one_rewarded_attempts_today",
    ):
        op.drop_column("users", name)
    # Postgres cannot drop an enum value — 'one_on_one' stays in game_type_enum.
