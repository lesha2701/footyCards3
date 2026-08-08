"""Admin-triggered maintenance banner in the Mini App

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("maintenance_banner_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("game_config", "maintenance_banner_until")
