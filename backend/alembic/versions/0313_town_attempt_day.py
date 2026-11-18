"""«Жители города» game_attempts (Матилде): one extra rewarded attempt a day
for one game — the day and the game that took it on the user.

Revision ID: 0313
Revises: 0312
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0313"
down_revision: Union[str, None] = "0312"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("town_attempt_day", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("town_attempt_game", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "town_attempt_game")
    op.drop_column("users", "town_attempt_day")
