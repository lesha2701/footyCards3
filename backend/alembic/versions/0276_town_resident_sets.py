"""«Наборы жителей»: a resident belongs to a named set (town_residents.set_name);
a town holding every active resident of a set gets a rent bonus and a badge.

Revision ID: 0276
Revises: 0275
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0276"
down_revision: Union[str, None] = "0275"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("town_residents", sa.Column("set_name", sa.String(48), nullable=True))


def downgrade() -> None:
    op.drop_column("town_residents", "set_name")
