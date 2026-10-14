"""«Химия карточек»: «тренер-земляк» (coaches.country) and «домашний стадион»
(stadiums.club) plus their GameConfig extras. NULL country/club = no extra.

Revision ID: 0140
Revises: 0139
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0140"
down_revision: Union[str, None] = "0139"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("coaches", sa.Column("country", sa.String(64), nullable=True))
    op.add_column("stadiums", sa.Column("club", sa.String(64), nullable=True))
    op.add_column("game_config", sa.Column("chemistry_coach_country_points", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("chemistry_stadium_club_points", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("game_config", "chemistry_stadium_club_points")
    op.drop_column("game_config", "chemistry_coach_country_points")
    op.drop_column("stadiums", "club")
    op.drop_column("coaches", "country")
