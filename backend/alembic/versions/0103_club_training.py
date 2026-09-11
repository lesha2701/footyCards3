"""Club training mechanic — TournamentClubStanding.training_uses_remaining/training_boost_round,
GameConfig.club_training_boost_pct/club_training_uses_per_tournament

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: Union[str, None] = "0102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tournament_club_standings", sa.Column("training_uses_remaining", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("tournament_club_standings", sa.Column("training_boost_round", sa.Integer(), nullable=True))

    op.add_column("game_config", sa.Column("club_training_boost_pct", sa.Numeric(4, 2), nullable=False, server_default="0.10"))
    op.add_column("game_config", sa.Column("club_training_uses_per_tournament", sa.Integer(), nullable=False, server_default="3"))


def downgrade() -> None:
    op.drop_column("game_config", "club_training_uses_per_tournament")
    op.drop_column("game_config", "club_training_boost_pct")
    op.drop_column("tournament_club_standings", "training_boost_round")
    op.drop_column("tournament_club_standings", "training_uses_remaining")
