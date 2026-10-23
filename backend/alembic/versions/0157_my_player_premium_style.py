"""«Мой игрок»: premium hairstyles and accessories for Stars

Revision ID: 0157
Revises: 0156
Create Date: 2026-10-17

Adds the Stars prices of the new «Раздевалка» items (Neymar's hairstyle,
Ronaldo's slick, Pogba's dyed fade, star aviators, a diamond chain) to
game_config.my_player_cosmetic_stars_prices, keeping any price an admin
already set. Each item also adds «статус» (my_player_service.COSMETIC_STATUS).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0157"
down_revision: Union[str, None] = "0156"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = '{"hair_neymar": 120, "hair_cr7": 100, "hair_pogba": 90, "aviators": 60, "diamond_chain": 90}'


def upgrade() -> None:
    op.execute(
        f"UPDATE game_config SET my_player_cosmetic_stars_prices = "
        f"('{NEW}'::jsonb || COALESCE(my_player_cosmetic_stars_prices::jsonb, '{{}}'::jsonb))::json"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE game_config SET my_player_cosmetic_stars_prices = (my_player_cosmetic_stars_prices::jsonb "
        "- 'hair_neymar' - 'hair_cr7' - 'hair_pogba' - 'aviators' - 'diamond_chain')::json"
    )
