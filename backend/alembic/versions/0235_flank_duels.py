"""Flank duels of «Карьера тренера»: a duel style per footballer (NULL =
derived), known rivalries set in the admin, the global duel history and the
GameConfig switch (services/duel_service.py).

Revision ID: 0235
Revises: 0234
Create Date: 2026-10-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0235"
down_revision: Union[str, None] = "0234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("duel_style", sa.String(16), nullable=True))
    op.create_table(
        "player_rivalries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attacker_key", sa.String(128), nullable=False),
        sa.Column("defender_key", sa.String(128), nullable=False),
        sa.Column("attacker_name", sa.String(128), nullable=False),
        sa.Column("defender_name", sa.String(128), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attacker_key", "defender_key", name="uq_player_rivalries_pair"),
    )
    op.create_index("ix_player_rivalries_attacker_key", "player_rivalries", ["attacker_key"])
    op.create_index("ix_player_rivalries_defender_key", "player_rivalries", ["defender_key"])
    op.create_table(
        "duel_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("attacker_key", sa.String(128), nullable=False),
        sa.Column("defender_key", sa.String(128), nullable=False),
        sa.Column("attacker_wins", sa.Float(), nullable=False, server_default="0"),
        sa.Column("defender_wins", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("attacker_key", "defender_key", name="uq_duel_history_pair"),
    )
    op.add_column("game_config", sa.Column("career_duels_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("game_config", "career_duels_enabled")
    op.drop_table("duel_history")
    op.drop_index("ix_player_rivalries_defender_key", table_name="player_rivalries")
    op.drop_index("ix_player_rivalries_attacker_key", table_name="player_rivalries")
    op.drop_table("player_rivalries")
    op.drop_column("players", "duel_style")
