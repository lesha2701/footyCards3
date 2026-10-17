"""«Статус» for everything sold for Stars

Revision ID: 0158
Revises: 0157
Create Date: 2026-10-17

«Мой игрок»'s «статус» (lifestyle_service.prestige) now also counts:
artifacts and «Стиль» cosmetics a player owns (a new `status` per item,
editable in the admin panel), an active «Клубный абонемент» and the premium
track of the current season (GameConfig.club_pass_status /
season_premium_status). Starting values: artifacts by rarity, cosmetics
from their Stars price.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0158"
down_revision: Union[str, None] = "0157"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("status", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("cosmetics", sa.Column("status", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_config", sa.Column("club_pass_status", sa.Integer(), nullable=False, server_default="50"))
    op.add_column("game_config", sa.Column("season_premium_status", sa.Integer(), nullable=False, server_default="30"))
    op.execute(
        """
        UPDATE artifacts SET status = CASE rarity
            WHEN 'diamond' THEN 40 WHEN 'legendary' THEN 30 WHEN 'epic' THEN 20 WHEN 'rare' THEN 10 ELSE 5 END
        """
    )
    op.execute(
        """
        UPDATE cosmetics SET status = CASE
            WHEN is_exclusive THEN 15
            WHEN stars_price > 0 THEN GREATEST(5, stars_price / 3)
            ELSE 5 END
        """
    )


def downgrade() -> None:
    op.drop_column("game_config", "season_premium_status")
    op.drop_column("game_config", "club_pass_status")
    op.drop_column("cosmetics", "status")
    op.drop_column("artifacts", "status")
