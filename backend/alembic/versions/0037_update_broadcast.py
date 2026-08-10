"""Admin update broadcasts (bot message + in-app "update available" banner)

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("last_update_broadcast_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("game_config", "last_update_broadcast_at")
