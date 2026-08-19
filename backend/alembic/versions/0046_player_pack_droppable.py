"""player is_pack_droppable flag

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    op.drop_column("players", "is_pack_droppable")
