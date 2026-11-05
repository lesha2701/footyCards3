"""«Ферги Тайм» pays: users' hourly/daily counters and the GameConfig settings
(a flat fee for a match played to the end, the daily cap).

Revision ID: 0258
Revises: 0257
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0258"
down_revision: Union[str, None] = "0257"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("fergie_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("fergie_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("fergie_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("fergie_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("fergie_match_coins", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("fergie_daily_limit", sa.Integer(), nullable=False, server_default="5"))


def downgrade() -> None:
    op.drop_column("game_config", "fergie_daily_limit")
    op.drop_column("game_config", "fergie_match_coins")
    op.drop_column("users", "fergie_hour_started_at")
    op.drop_column("users", "fergie_hourly_attempts")
    op.drop_column("users", "fergie_attempts_reset_at")
    op.drop_column("users", "fergie_rewarded_attempts_today")
