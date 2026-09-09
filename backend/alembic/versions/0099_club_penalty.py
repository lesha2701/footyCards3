"""Club Penalty — replaces "Что исчезло?" as the third club mini-game

Revision ID: 0099
Revises: 0098
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0099"
down_revision: Union[str, None] = "0098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("club_penalty_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_penalty_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_penalty_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_penalty_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_penalty_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_penalty_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_penalty_reward_win", sa.Integer(), nullable=False, server_default="45"))
    op.add_column("game_config", sa.Column("club_penalty_reward_loss", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("club_penalty_bot_miss_chance", sa.Numeric(4, 2), nullable=False, server_default="0.12"))


def downgrade() -> None:
    op.drop_column("users", "club_penalty_rewarded_attempts_today")
    op.drop_column("users", "club_penalty_attempts_reset_at")
    op.drop_column("users", "club_penalty_hourly_attempts")
    op.drop_column("users", "club_penalty_hour_started_at")

    op.drop_column("game_config", "club_penalty_hourly_limit")
    op.drop_column("game_config", "club_penalty_daily_reward_limit")
    op.drop_column("game_config", "club_penalty_reward_win")
    op.drop_column("game_config", "club_penalty_reward_loss")
    op.drop_column("game_config", "club_penalty_bot_miss_chance")
