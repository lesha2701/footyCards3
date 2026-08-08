"""Найди пару: tiered reward brackets instead of a linear per-mistake penalty

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("pairs_error_bracket_size", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("pairs_bracket_penalty", sa.Integer(), nullable=False, server_default="10"))
    op.drop_column("game_config", "pairs_penalty_per_wrong")

    # Existing "perfect run" reward was tuned for the old linear formula
    # (default 60); the new bracket example (40 / 30 / 20 / ... floored at
    # pairs_reward_min) reads better starting from 40.
    op.execute("UPDATE game_config SET pairs_reward_perfect = 40 WHERE pairs_reward_perfect = 60")


def downgrade() -> None:
    op.execute("UPDATE game_config SET pairs_reward_perfect = 60 WHERE pairs_reward_perfect = 40")
    op.add_column("game_config", sa.Column("pairs_penalty_per_wrong", sa.Integer(), nullable=False, server_default="3"))
    op.drop_column("game_config", "pairs_bracket_penalty")
    op.drop_column("game_config", "pairs_error_bracket_size")
