"""rework saboteur into a steward-dodging ladder (line-of-5, escalating per-level reward)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "saboteur_cell_reward", new_column_name="saboteur_line_base_reward")
    op.alter_column("game_config", "saboteur_max_bomb_count", new_column_name="saboteur_max_steward_count")
    op.add_column(
        "game_config", sa.Column("saboteur_line_growth", sa.Numeric(4, 2), nullable=False, server_default="1.15")
    )


def downgrade() -> None:
    op.drop_column("game_config", "saboteur_line_growth")
    op.alter_column("game_config", "saboteur_max_steward_count", new_column_name="saboteur_max_bomb_count")
    op.alter_column("game_config", "saboteur_line_base_reward", new_column_name="saboteur_cell_reward")
