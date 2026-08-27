"""Tournament, TournamentClub

Revision ID: 0066
Revises: 0065
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Enum("active", "completed", name="tournament_status_enum"), nullable=False, server_default="active"),
        sa.Column("rounds_simulated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rounds_simulated >= 0 AND rounds_simulated <= 14", name="ck_tournaments_rounds_simulated_range"),
    )
    op.create_table(
        "tournament_clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_withdrawn", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("tournament_id", "club_id", name="uq_tournament_clubs_once"),
    )
    op.create_index("ix_tournament_clubs_tournament_id", "tournament_clubs", ["tournament_id"])
    op.create_index("ix_tournament_clubs_club_id", "tournament_clubs", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_tournament_clubs_club_id", table_name="tournament_clubs")
    op.drop_index("ix_tournament_clubs_tournament_id", table_name="tournament_clubs")
    op.drop_table("tournament_clubs")
    op.drop_table("tournaments")
    bind = op.get_bind()
    sa.Enum(name="tournament_status_enum").drop(bind, checkfirst=True)
