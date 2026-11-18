"""«Табло удачи»: up to 25 Stars spins a day and no hourly cap
(lucky_board_hourly_limit 0 = no cap).

Revision ID: 0318
Revises: 0317
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0318"
down_revision: Union[str, None] = "0317"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "lucky_board_paid_daily_limit", server_default="25")
    op.alter_column("game_config", "lucky_board_hourly_limit", server_default="0")
    op.execute(sa.text("UPDATE game_config SET lucky_board_paid_daily_limit = 25, lucky_board_hourly_limit = 0"))


def downgrade() -> None:
    op.alter_column("game_config", "lucky_board_paid_daily_limit", server_default="20")
    op.alter_column("game_config", "lucky_board_hourly_limit", server_default="10")
    op.execute(sa.text("UPDATE game_config SET lucky_board_paid_daily_limit = 20, lucky_board_hourly_limit = 10"))
