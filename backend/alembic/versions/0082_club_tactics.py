"""Add club formation/mentality/playstyle + tactical engine config fields

Revision ID: 0082
Revises: 0081
Create Date: 2026-08-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0082"
down_revision: Union[str, None] = "0081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("formation", sa.String(length=16), nullable=False, server_default="4-3-3"))
    op.add_column("club_lineups", sa.Column("mentality", sa.String(length=16), nullable=False, server_default="BALANCED"))
    op.add_column("club_lineups", sa.Column("playstyle", sa.String(length=16), nullable=False, server_default="CENTRAL_PLAY"))

    op.add_column("game_config", sa.Column("club_tactical_phases_per_match_min", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("club_tactical_phases_per_match_max", sa.Integer(), nullable=False, server_default="70"))
    op.add_column("game_config", sa.Column("club_tactical_promoted_chance_target_min", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("club_tactical_promoted_chance_target_max", sa.Integer(), nullable=False, server_default="25"))
    op.add_column("game_config", sa.Column("club_tactical_fit_formation_weight", sa.Numeric(4, 2), nullable=False, server_default="0.40"))
    op.add_column("game_config", sa.Column("club_tactical_fit_playstyle_weight", sa.Numeric(4, 2), nullable=False, server_default="0.40"))
    op.add_column("game_config", sa.Column("club_tactical_fit_mentality_weight", sa.Numeric(4, 2), nullable=False, server_default="0.20"))


def downgrade() -> None:
    op.drop_column("game_config", "club_tactical_fit_mentality_weight")
    op.drop_column("game_config", "club_tactical_fit_playstyle_weight")
    op.drop_column("game_config", "club_tactical_fit_formation_weight")
    op.drop_column("game_config", "club_tactical_promoted_chance_target_max")
    op.drop_column("game_config", "club_tactical_promoted_chance_target_min")
    op.drop_column("game_config", "club_tactical_phases_per_match_max")
    op.drop_column("game_config", "club_tactical_phases_per_match_min")

    op.drop_column("club_lineups", "playstyle")
    op.drop_column("club_lineups", "mentality")
    op.drop_column("club_lineups", "formation")
