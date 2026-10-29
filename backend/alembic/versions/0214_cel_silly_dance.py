"""«Мой игрок»: the «Смешной танец» goal celebration for Stars

Revision ID: 0214
Revises: 0213
Create Date: 2026-10-29

Adds its Stars price to game_config.my_player_cosmetic_stars_prices,
keeping any price an admin already set. The kicker dances it after a goal
in the 3D shootout.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0214"
down_revision: Union[str, None] = "0213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = '{"cel_silly": 50}'


def upgrade() -> None:
    op.execute(
        f"UPDATE game_config SET my_player_cosmetic_stars_prices = "
        f"('{NEW}'::jsonb || COALESCE(my_player_cosmetic_stars_prices::jsonb, '{{}}'::jsonb))::json"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE game_config SET my_player_cosmetic_stars_prices = "
        "(my_player_cosmetic_stars_prices::jsonb - 'cel_silly')::json"
    )
