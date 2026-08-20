"""Leagues: swap free-text emoji icon for an admin-set trophy color, and
track whether a player has visually acknowledged a reward claim

Revision ID: 0048
Revises: 0047
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0048"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "league_tiers", "icon", new_column_name="color",
        server_default="#94a3b8",
    )
    op.add_column(
        "user_league_reward_claims",
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_league_reward_claims", "seen_at")
    op.alter_column(
        "league_tiers", "color", new_column_name="icon",
        server_default="🏅",
    )
