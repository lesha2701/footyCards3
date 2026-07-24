"""economy rebalance and saboteur difficulty

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "game_config", sa.Column("saboteur_max_bomb_count", sa.Integer(), nullable=False, server_default="4")
    )

    op.execute(
        """UPDATE game_config SET
               memory_reward_cap = 150,
               match_reward_win = 25,
               match_reward_draw = 12,
               match_reward_loss = 5,
               saboteur_cell_reward = 8,
               penalty_reward_win = 45,
               penalty_reward_draw = 18,
               penalty_reward_loss = 8,
               free_kick_base_stake = 15,
               free_pack_interval_hours = 8
           WHERE id = 1"""
    )


def downgrade() -> None:
    op.execute(
        """UPDATE game_config SET
               memory_reward_cap = 500,
               match_reward_win = 100,
               match_reward_draw = 40,
               match_reward_loss = 10,
               saboteur_cell_reward = 10,
               penalty_reward_win = 150,
               penalty_reward_draw = 60,
               penalty_reward_loss = 15,
               free_kick_base_stake = 40,
               free_pack_interval_hours = 3
           WHERE id = 1"""
    )

    op.drop_column("game_config", "saboteur_max_bomb_count")
