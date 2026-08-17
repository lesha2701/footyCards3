"""feature flags and per-user trade ban

Revision ID: 0045
Revises: 0044
Create Date: 2026-08-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("matchmaking_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("game_config", sa.Column("wheel_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("is_trade_banned", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "is_trade_banned")
    op.drop_column("game_config", "wheel_enabled")
    op.drop_column("game_config", "matchmaking_enabled")
