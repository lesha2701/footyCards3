"""«Филиал академии»: the Stars side (credits, the academy's name, skins).

Revision ID: 0323
Revises: 0322
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0323"
down_revision: Union[str, None] = "0322"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("manager_filials", sa.Column("extras", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("manager_filials", "extras")
