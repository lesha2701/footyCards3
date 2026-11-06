"""Notifications held back until a moment: a career round's result is known
when its second half kicks off, the coach hears it after the broadcast.

Revision ID: 0260
Revises: 0259
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0260"
down_revision: Union[str, None] = "0259"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("deliver_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "deliver_after")
