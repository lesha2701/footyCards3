"""Trades: switch off coins and require cards on both sides.

Revision ID: 0166
Revises: 0165
Create Date: 2026-10-18

For now trades are card-for-card only: coins in trades (either side) and
one-way card gifts are off, both behind admin switches so they can be turned
back on without a deploy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0166"
down_revision: Union[str, None] = "0165"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("trade_coins_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("trade_cards_both_sides", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("game_config", "trade_cards_both_sides")
    op.drop_column("game_config", "trade_coins_enabled")
