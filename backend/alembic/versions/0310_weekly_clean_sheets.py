"""«Карьера игрока»: the first weekly task follows the player's line —
defenders and goalkeepers keep clean sheets instead of scoring
(game_config.player_career_weekly_clean_sheets).

Revision ID: 0310
Revises: 0309
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0310"
down_revision: Union[str, None] = "0309"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("player_career_weekly_clean_sheets", sa.Integer(), nullable=False, server_default="3"))


def downgrade() -> None:
    op.drop_column("game_config", "player_career_weekly_clean_sheets")
