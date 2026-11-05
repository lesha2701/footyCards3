"""«Ответка»: the game type, users' hourly/daily counters and the GameConfig
settings (daily cap, coins, how often the bot answers).

Revision ID: 0255
Revises: 0254
Create Date: 2026-11-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0255"
down_revision: Union[str, None] = "0254"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("otvetka_daily_limit", "5"),
    ("otvetka_goal_coins", "15"),
    ("otvetka_win_coins", "150"),
    ("otvetka_loss_coins", "30"),
    ("otvetka_bot_goal_pct", "35"),
    ("otvetka_bot_penalty_pct", "70"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'otvetka'")
    op.add_column("users", sa.Column("otvetka_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("otvetka_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("otvetka_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("otvetka_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    for name in (
        "otvetka_hour_started_at", "otvetka_hourly_attempts",
        "otvetka_attempts_reset_at", "otvetka_rewarded_attempts_today",
    ):
        op.drop_column("users", name)
    # Postgres cannot drop an enum value — 'otvetka' stays in game_type_enum.
