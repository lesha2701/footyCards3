"""Add diamond rarity above legendary

Revision ID: 0083
Revises: 0081
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0083"
down_revision: Union[str, None] = "0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE rarity_enum ADD VALUE IF NOT EXISTS 'diamond'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0010_card_upgrade.py's identical note).
    pass
