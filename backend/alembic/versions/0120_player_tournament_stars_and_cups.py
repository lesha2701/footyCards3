"""Player tournaments: rename the single rating to stars (matching Club.stars_count),
add cups (matching Club.cups_count), and backfill both from history already on this branch.

Revision ID: 0120
Revises: 0119
Create Date: 2026-09-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0120"
down_revision: Union[str, None] = "0119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "tournament_rating", new_column_name="tournament_stars_count")
    op.add_column("users", sa.Column("tournament_cups_count", sa.Integer(), nullable=False, server_default="0"))

    op.alter_column("game_config", "ptour_rating_by_place", new_column_name="ptour_stars_by_place")

    op.alter_column("player_tournament_results", "rating_delta", new_column_name="stars_delta")
    op.add_column("player_tournament_results", sa.Column("cup_awarded", sa.Boolean(), nullable=False, server_default="false"))

    # Backfill: any tournament concluded before this migration only set rating_delta/final_rank,
    # never cup_awarded (the column didn't exist) and never touched tournament_cups_count. Both
    # need to reflect history, not just future conclusions.
    op.execute("UPDATE player_tournament_results SET cup_awarded = true WHERE final_rank = 1")
    op.execute(
        """
        UPDATE users SET tournament_cups_count = tournament_cups_count + sub.cnt
        FROM (
            SELECT user_id, COUNT(*) AS cnt FROM player_tournament_results WHERE final_rank = 1 GROUP BY user_id
        ) AS sub
        WHERE users.id = sub.user_id
        """
    )


def downgrade() -> None:
    op.drop_column("player_tournament_results", "cup_awarded")
    op.alter_column("player_tournament_results", "stars_delta", new_column_name="rating_delta")

    op.alter_column("game_config", "ptour_stars_by_place", new_column_name="ptour_rating_by_place")

    op.drop_column("users", "tournament_cups_count")
    op.alter_column("users", "tournament_stars_count", new_column_name="tournament_rating")
