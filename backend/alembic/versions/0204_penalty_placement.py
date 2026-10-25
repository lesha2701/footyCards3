"""GameConfig.penalty_placement_max_pct: vs the bot, a strong shooter
sometimes scores although the keeper guessed the corner (% at rating 99,
0 at 58).

Revision ID: 0204
Revises: 0203
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0204"
down_revision: Union[str, None] = "0203"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_config", sa.Column("penalty_placement_max_pct", sa.Integer(), nullable=False, server_default="15"),
    )


def downgrade() -> None:
    op.drop_column("game_config", "penalty_placement_max_pct")
