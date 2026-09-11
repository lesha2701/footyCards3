"""New minigame: Своя позиция (position match)

Revision ID: 0107
Revises: 0106
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0107"
down_revision: Union[str, None] = "0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'position_match'")

    op.add_column("users", sa.Column("position_match_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("position_match_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("position_match_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("position_match_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("position_match_daily_limit", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("position_match_max_mistakes", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("position_match_reward_perfect", sa.Integer(), nullable=False, server_default="35"))
    op.add_column("game_config", sa.Column("position_match_reward_min", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("position_match_penalty_per_mistake", sa.Integer(), nullable=False, server_default="8"))


def downgrade() -> None:
    op.drop_column("game_config", "position_match_penalty_per_mistake")
    op.drop_column("game_config", "position_match_reward_min")
    op.drop_column("game_config", "position_match_reward_perfect")
    op.drop_column("game_config", "position_match_max_mistakes")
    op.drop_column("game_config", "position_match_daily_limit")

    op.drop_column("users", "position_match_hour_started_at")
    op.drop_column("users", "position_match_hourly_attempts")
    op.drop_column("users", "position_match_attempts_reset_at")
    op.drop_column("users", "position_match_rewarded_attempts_today")

    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'position_match' on
    # the enum on downgrade is harmless (mirrors 0030's card_pairs note).
