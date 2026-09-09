"""Drop the now-dead club_missing_item_* columns — club_missing_item_service is
removed in this same commit, so nothing reads or writes them any more

Revision ID: 0100
Revises: 0099
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0100"
down_revision: Union[str, None] = "0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("users", "club_missing_item_rewarded_attempts_today")
    op.drop_column("users", "club_missing_item_attempts_reset_at")
    op.drop_column("users", "club_missing_item_hourly_attempts")
    op.drop_column("users", "club_missing_item_hour_started_at")

    op.drop_column("game_config", "club_missing_item_hourly_limit")
    op.drop_column("game_config", "club_missing_item_daily_reward_limit")
    op.drop_column("game_config", "club_missing_item_reward_cap")


def downgrade() -> None:
    op.add_column("users", sa.Column("club_missing_item_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_missing_item_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_missing_item_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_missing_item_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_missing_item_reward_cap", sa.Integer(), nullable=False, server_default="100"))
