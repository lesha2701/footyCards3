"""Lock cards used in a Tactico squad against trade/upgrade/sell

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("is_in_tactico_squad", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("user_cards", "is_in_tactico_squad")
