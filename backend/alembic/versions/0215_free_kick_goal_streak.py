"""«Штрафной 3D»: «Серия без промахов» — goals in a row per user, bonus
coins on the 3rd, 5th and 10th (then every 10th).

Revision ID: 0215
Revises: 0214
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0215"
down_revision: Union[str, None] = "0214"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG = {
    "free_kick_streak_3_bonus": 15,
    "free_kick_streak_5_bonus": 40,
    "free_kick_streak_10_bonus": 120,
}


def upgrade() -> None:
    for name, default in CONFIG.items():
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=str(default)))
    op.add_column("users", sa.Column("free_kick_goal_streak", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "free_kick_goal_streak")
    for name in reversed(list(CONFIG)):
        op.drop_column("game_config", name)
