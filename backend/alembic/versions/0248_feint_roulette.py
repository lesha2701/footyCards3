"""«Мой игрок»: the «Рулетка» feint for «Атака 1 на 1», for Stars

Revision ID: 0248
Revises: 0247
Create Date: 2026-11-03

Adds its Stars price to game_config.my_player_cosmetic_stars_prices,
keeping any price an admin already set.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0248"
down_revision: Union[str, None] = "0247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = '{"feint_roulette": 75}'


def upgrade() -> None:
    op.execute(
        f"UPDATE game_config SET my_player_cosmetic_stars_prices = "
        f"('{NEW}'::jsonb || COALESCE(my_player_cosmetic_stars_prices::jsonb, '{{}}'::jsonb))::json"
    )


def downgrade() -> None:
    op.execute("UPDATE game_config SET my_player_cosmetic_stars_prices = (my_player_cosmetic_stars_prices::jsonb - 'feint_roulette')::json")
