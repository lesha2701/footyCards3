"""arena goals counters

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("goals_for", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("goals_against", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "goals_against")
    op.drop_column("users", "goals_for")
