"""Bingo: more goal types (rare/epic drops, penalty, Card Arena)

Revision ID: 0087
Revises: 0086
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0087"
down_revision: Union[str, None] = "0086"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE bingo_goal_type_enum ADD VALUE IF NOT EXISTS 'rare_drops'")
    op.execute("ALTER TYPE bingo_goal_type_enum ADD VALUE IF NOT EXISTS 'epic_drops'")
    op.execute("ALTER TYPE bingo_goal_type_enum ADD VALUE IF NOT EXISTS 'penalty_matches_played'")
    op.execute("ALTER TYPE bingo_goal_type_enum ADD VALUE IF NOT EXISTS 'arena_matches_played'")


def downgrade() -> None:
    # No DROP VALUE in Postgres — same convention as every other additive
    # enum value in this codebase (see 0083_diamond_rarity.py).
    pass
