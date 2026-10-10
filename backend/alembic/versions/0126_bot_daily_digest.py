"""Bot daily digest switch and hour on game_config (off by default).

Revision ID: 0126
Revises: 0125
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0126"
down_revision: Union[str, None] = "0125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("bot_daily_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("bot_daily_digest_hour", sa.Integer(), nullable=False, server_default="18"))


def downgrade() -> None:
    op.drop_column("game_config", "bot_daily_digest_hour")
    op.drop_column("game_config", "bot_daily_digest_enabled")
