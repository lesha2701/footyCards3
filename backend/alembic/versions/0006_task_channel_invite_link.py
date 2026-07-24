"""task channel invite link

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task_definitions", sa.Column("invite_link", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("task_definitions", "invite_link")
