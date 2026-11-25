"""Passing an owned collectible gift on for Stars: game_config.gift_transfer_stars

Revision ID: 0338
Revises: 0337
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0338"
down_revision: Union[str, None] = "0337"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("gift_transfer_stars", sa.Integer(), nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("game_config", "gift_transfer_stars")
