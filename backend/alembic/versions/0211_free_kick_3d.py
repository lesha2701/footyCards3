"""«Штрафной 3D» replaces the old free kick: its own hourly cap of series,
the series length and the coins per kick on game_config.

Revision ID: 0211
Revises: 0210
Create Date: 2026-10-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0211"
down_revision: Union[str, None] = "0210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = {
    "free_kick_hourly_limit": 1,
    "free_kick_3d_kicks": 5,
    "free_kick_3d_goal_coins": 20,
    "free_kick_3d_corner_bonus": 10,
    "free_kick_3d_curl_bonus": 5,
    "free_kick_3d_near_coins": 3,
}


def upgrade() -> None:
    for name, default in COLUMNS.items():
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=str(default)))


def downgrade() -> None:
    for name in reversed(list(COLUMNS)):
        op.drop_column("game_config", name)
