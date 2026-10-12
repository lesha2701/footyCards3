"""«Химия карточек», этап 2: the rules each CLUB tournament froze at its start
(NULL = off), mirroring player_tournaments.chemistry_rules from 0136.

Revision ID: 0137
Revises: 0136
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0137"
down_revision: Union[str, None] = "0136"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("chemistry_rules", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "chemistry_rules")
