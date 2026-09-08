"""ClubLineup.club_coach_card_id

Revision ID: 0093
Revises: 0092
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("club_lineups", sa.Column("club_coach_card_id", sa.Integer(), sa.ForeignKey("club_coach_cards.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_club_lineups_club_coach_card_id", "club_lineups", ["club_coach_card_id"])


def downgrade() -> None:
    op.drop_index("ix_club_lineups_club_coach_card_id", table_name="club_lineups")
    op.drop_column("club_lineups", "club_coach_card_id")
