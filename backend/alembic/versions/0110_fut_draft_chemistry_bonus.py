"""FUT Draft: dedicated (bigger) club/country chemistry bonus on top of
calculate_base_strength's own, much smaller built-in one.

Revision ID: 0110
Revises: 0109
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0110"
down_revision: Union[str, None] = "0109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("fut_draft_club_bonus_per_extra", sa.Integer(), nullable=False, server_default="12"))
    op.add_column("game_config", sa.Column("fut_draft_country_bonus_per_extra", sa.Integer(), nullable=False, server_default="6"))


def downgrade() -> None:
    op.drop_column("game_config", "fut_draft_country_bonus_per_extra")
    op.drop_column("game_config", "fut_draft_club_bonus_per_extra")
