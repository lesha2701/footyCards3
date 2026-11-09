"""«Город»: the mood of districts. Care (user_towns.cared_at — the last time
the rent was collected), the houses, the places and the residents settled
in a district (user_town_residents.district) make its mood, and the mood
sets its houses' rent (town_service.district_moods, GameConfig.town_mood
over town_service.MOOD_DEFAULTS).

Revision ID: 0271
Revises: 0270
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0271"
down_revision: Union[str, None] = "0270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_towns", sa.Column("cared_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_town_residents", sa.Column("district", sa.String(16), nullable=True))
    op.add_column("game_config", sa.Column("town_mood", sa.JSON(), nullable=False, server_default="{}"))
    # A town already playing starts cared for.
    op.execute("UPDATE user_towns SET cared_at = now() WHERE unlocked_at IS NOT NULL")


def downgrade() -> None:
    op.drop_column("game_config", "town_mood")
    op.drop_column("user_town_residents", "district")
    op.drop_column("user_towns", "cared_at")
