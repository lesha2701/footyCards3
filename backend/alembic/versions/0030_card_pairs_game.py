"""New minigame: Найди пару (5x5 card pairs memory match)

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'card_pairs'")

    op.add_column("users", sa.Column("pairs_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("pairs_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("pairs_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("pairs_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("pairs_daily_limit", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("game_config", sa.Column("pairs_reward_perfect", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("game_config", sa.Column("pairs_reward_min", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("pairs_penalty_per_wrong", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("pairs_bonus_coins", sa.Integer(), nullable=False, server_default="25"))


def downgrade() -> None:
    op.drop_column("game_config", "pairs_bonus_coins")
    op.drop_column("game_config", "pairs_penalty_per_wrong")
    op.drop_column("game_config", "pairs_reward_min")
    op.drop_column("game_config", "pairs_reward_perfect")
    op.drop_column("game_config", "pairs_daily_limit")

    op.drop_column("users", "pairs_hour_started_at")
    op.drop_column("users", "pairs_hourly_attempts")
    op.drop_column("users", "pairs_attempts_reset_at")
    op.drop_column("users", "pairs_rewarded_attempts_today")

    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'card_pairs' on the
    # enum on downgrade is harmless (mirrors 0009's football_hangman note).
