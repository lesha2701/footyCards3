"""«Контратака»: defence log + revenge, weekly arena leagues.

Revision ID: 0285
Revises: 0284
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0285"
down_revision: Union[str, None] = "0284"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEAGUES = "[[0, 0], [1060, 150], [1140, 300], [1240, 600], [1360, 1000]]"


def upgrade() -> None:
    op.add_column("users", sa.Column("kontra_defense_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("kontra_week", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("kontra_week_best", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("kontra_league_reward", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("kontra_leagues", sa.JSON(), nullable=False, server_default=LEAGUES))
    op.add_column("game_config", sa.Column("kontra_tactic_edge_pct", sa.Integer(), nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("game_config", "kontra_tactic_edge_pct")
    op.drop_column("game_config", "kontra_leagues")
    op.drop_column("users", "kontra_league_reward")
    op.drop_column("users", "kontra_week_best")
    op.drop_column("users", "kontra_week")
    op.drop_column("users", "kontra_defense_seen_at")
