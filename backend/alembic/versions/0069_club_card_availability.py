"""ClubCardAvailability

Revision ID: 0069
Revises: 0068
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_card_availabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rounds_remaining", sa.Integer(), nullable=False),
        sa.UniqueConstraint("club_card_id", name="uq_club_card_availabilities_card"),
    )


def downgrade() -> None:
    op.drop_table("club_card_availabilities")
