"""TournamentMatch

Revision ID: 0067
Revises: 0066
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournament_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("club_a_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_b_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score_a", sa.Integer(), nullable=False),
        sa.Column("score_b", sa.Integer(), nullable=False),
        sa.Column("event_log", sa.JSON(), nullable=False),
        sa.Column("simulated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("round_number >= 1 AND round_number <= 14", name="ck_tournament_matches_round_range"),
    )
    op.create_index("ix_tournament_matches_tournament_id", "tournament_matches", ["tournament_id"])
    op.create_index("ix_tournament_matches_club_a_id", "tournament_matches", ["club_a_id"])
    op.create_index("ix_tournament_matches_club_b_id", "tournament_matches", ["club_b_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_matches_club_b_id", table_name="tournament_matches")
    op.drop_index("ix_tournament_matches_club_a_id", table_name="tournament_matches")
    op.drop_index("ix_tournament_matches_tournament_id", table_name="tournament_matches")
    op.drop_table("tournament_matches")
