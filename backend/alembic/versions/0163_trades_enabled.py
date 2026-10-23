"""game_config.trades_enabled — admin switch for player-to-player trades

Revision ID: 0163
Revises: 0162
Create Date: 2026-10-18

Off = nobody can create or accept trade offers (pending ones can still be
cancelled or rejected); used to stop coin selling from multi-accounts.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0163"
down_revision: Union[str, None] = "0162"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("trades_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("game_config", "trades_enabled")
