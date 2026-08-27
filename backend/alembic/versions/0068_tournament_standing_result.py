"""TournamentClubStanding, TournamentClubResult

Revision ID: 0068
Revises: 0067
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_club_standings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_for", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals_against", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_standings_once"),
    )
    op.create_table(
        "tournament_club_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("final_rank", sa.Integer(), nullable=False),
        sa.Column("budget_awarded", sa.Integer(), nullable=False),
        sa.Column("stars_delta", sa.Integer(), nullable=False),
        sa.Column("cup_awarded", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_club_results_once"),
    )
    op.create_index("ix_tournament_club_standings_tournament_id", "tournament_club_standings", ["tournament_id"])
    op.create_index("ix_tournament_club_standings_club_id", "tournament_club_standings", ["club_id"])
    op.create_index("ix_tournament_club_results_tournament_id", "tournament_club_results", ["tournament_id"])
    op.create_index("ix_tournament_club_results_club_id", "tournament_club_results", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_club_results_club_id", table_name="tournament_club_results")
    op.drop_index("ix_tournament_club_results_tournament_id", table_name="tournament_club_results")
    op.drop_index("ix_tournament_club_standings_club_id", table_name="tournament_club_standings")
    op.drop_index("ix_tournament_club_standings_tournament_id", table_name="tournament_club_standings")
    op.drop_table("tournament_club_results")
    op.drop_table("tournament_club_standings")
