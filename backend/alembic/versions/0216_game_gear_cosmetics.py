"""«Мой игрок»: gear for the 3D free kick and penalty — balls, boots and
keeper's gloves — for Stars

Revision ID: 0216
Revises: 0215
Create Date: 2026-10-30

Adds their Stars prices to game_config.my_player_cosmetic_stars_prices,
keeping any price an admin already set.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0216"
down_revision: Union[str, None] = "0215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW = (
    '{"ball_gold": 60, "ball_neon": 40, "ball_retro": 40, "boots_red": 30, "boots_neon": 40, "boots_gold": 60, '
    '"gloves_lime": 30, "gloves_pink": 30, "gloves_gold": 60}'
)
CODES = ("ball_gold", "ball_neon", "ball_retro", "boots_red", "boots_neon", "boots_gold", "gloves_lime", "gloves_pink", "gloves_gold")


def upgrade() -> None:
    op.execute(
        f"UPDATE game_config SET my_player_cosmetic_stars_prices = "
        f"('{NEW}'::jsonb || COALESCE(my_player_cosmetic_stars_prices::jsonb, '{{}}'::jsonb))::json"
    )


def downgrade() -> None:
    drop = " ".join(f"- '{c}'" for c in CODES)
    op.execute(f"UPDATE game_config SET my_player_cosmetic_stars_prices = (my_player_cosmetic_stars_prices::jsonb {drop})::json")
