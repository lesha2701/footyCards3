"""«Лига» keeps growing across weeks: users.league_points banks the game
ratings (arena + tactics + penalty) right before the Monday reset; the league
is league_points + those three. The points wiped by the first reset come back
from the backup with ops/restore_ratings.sh (data, run once on the server).

Revision ID: 0268
Revises: 0267
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0268"
down_revision: Union[str, None] = "0267"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("league_points", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "league_points")
