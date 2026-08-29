"""Add announcement_text/announcement_updated_at to game_config

Revision ID: 0079
Revises: 0078
Create Date: 2026-08-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0079"
down_revision: Union[str, None] = "0078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("announcement_text", sa.String(length=500), nullable=True))
    op.add_column("game_config", sa.Column("announcement_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("game_config", "announcement_updated_at")
    op.drop_column("game_config", "announcement_text")
