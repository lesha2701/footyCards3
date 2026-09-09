"""Add the missing club_penalty / club_penalty_reward Postgres enum values

0099_club_penalty.py added GameType.club_penalty and
ClubBudgetTransactionType.club_penalty_reward to the Python enums and to the
services/tests that use them, but never ran the ALTER TYPE ... ADD VALUE
statements that make Postgres's native enum types actually accept those
values — unlike 0074_club_sequence_game.py and 0081_club_missing_item_game.py,
which both do this for their own new enum members. Invisible to the SQLite
test suite (no native enum type there); on real Postgres, every
POST /clubs/me/penalty/start 500s with "invalid input value for enum
game_type_enum: club_penalty" until this migration runs. 0099 is already
applied to this environment, so the fix has to be a new forward migration,
not an edit to 0099 itself.

Revision ID: 0101
Revises: 0100
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0101"
down_revision: Union[str, None] = "0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'club_penalty'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'club_penalty_reward'")


def downgrade() -> None:
    # Postgres cannot drop a single enum value once added (no ALTER TYPE ...
    # DROP VALUE) — same established rule as the ClubBudgetTransactionType
    # comment in models/enums.py. Nothing to do here; the values simply stay,
    # matching how every other ADD VALUE migration in this series (e.g. 0074,
    # 0081) handles its own downgrade().
    pass
