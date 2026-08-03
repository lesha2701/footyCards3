"""Foundation for new task types: same-country lineup, penalty win with a
low-rated player, and lifetime counters for clean-sheet wins / Memory
Sequence levels / Saboteur stewards passed.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE task_condition_type_enum ADD VALUE IF NOT EXISTS 'match_same_country'")
    op.execute("ALTER TYPE task_condition_type_enum ADD VALUE IF NOT EXISTS 'penalty_win_max_rating'")

    op.add_column("users", sa.Column("arena_clean_sheet_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("memory_levels_completed", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("saboteur_levels_cleared", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "saboteur_levels_cleared")
    op.drop_column("users", "memory_levels_completed")
    op.drop_column("users", "arena_clean_sheet_wins")

    # Postgres has no ALTER TYPE ... DROP VALUE; leaving the enum values in
    # place on downgrade is harmless (mirrors 0009's football_hangman note).
