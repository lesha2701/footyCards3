"""Тактико follow-ups: hourly play limit, squad rarity cap

Adds an hourly play limit for Tactico bot/friend match creation (mirroring
every other mini-game's `*_hourly_attempts`/`*_hour_started_at` pair) and
admin-tunable caps on how many legendary/epic cards a squad may contain,
so a player's raw collection power doesn't automatically decide matches.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tactico_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("tactico_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "game_config", sa.Column("tactico_max_legendary_cards", sa.Integer(), nullable=False, server_default="3")
    )
    op.add_column(
        "game_config", sa.Column("tactico_max_epic_cards", sa.Integer(), nullable=False, server_default="3")
    )


def downgrade() -> None:
    op.drop_column("game_config", "tactico_max_epic_cards")
    op.drop_column("game_config", "tactico_max_legendary_cards")

    op.drop_column("users", "tactico_hour_started_at")
    op.drop_column("users", "tactico_hourly_attempts")
