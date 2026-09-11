"""Admin-adjustment club budget transactions — ClubBudgetTransactionType.admin_adjustment

Revision ID: 0106
Revises: 0105
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0106"
down_revision: Union[str, None] = "0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'admin_adjustment'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — the added enum value is left in place on
    # downgrade, matching this repo's own established precedent (see migration 0102's downgrade
    # for the exact same situation with club_budget_transaction_type_enum).
    pass
