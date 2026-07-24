"""trade privacy settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("accept_trades", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("user_cards", sa.Column("hidden_from_trade", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("user_cards", "hidden_from_trade")
    op.drop_column("users", "accept_trades")
