"""«Химия карточек»: GameConfig switch and tuning for neighbour-link chemistry,
plus the rules each player tournament froze at its start (NULL = off).

Revision ID: 0136
Revises: 0135
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0136"
down_revision: Union[str, None] = "0135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INT_COLUMNS = {
    "chemistry_link_strong": "2",
    "chemistry_link_medium": "1",
    "chemistry_threshold_1": "1",
    "chemistry_threshold_2": "2",
    "chemistry_threshold_3": "4",
    "chemistry_player_max": "3",
    "chemistry_player_floor": "0",
    "chemistry_rating_per_point": "1",
    "chemistry_off_position_penalty": "0",
}


def upgrade() -> None:
    op.add_column("game_config", sa.Column("chemistry_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, default in _INT_COLUMNS.items():
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("player_tournaments", sa.Column("chemistry_rules", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("player_tournaments", "chemistry_rules")
    for name in reversed(list(_INT_COLUMNS)):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "chemistry_enabled")
