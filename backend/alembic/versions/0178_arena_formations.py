"""Card Arena formations: GameConfig scale of the formation attack/defense
tilt (lineups already store their formation; it stays 4-3-3 until changed).

Revision ID: 0178
Revises: 0177
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0178"
down_revision: Union[str, None] = "0177"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_config", sa.Column("arena_formation_effect_pct", sa.Integer(), nullable=False, server_default="100"),
    )


def downgrade() -> None:
    op.drop_column("game_config", "arena_formation_effect_pct")
