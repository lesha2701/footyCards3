"""ClubCoachCard

Revision ID: 0091
Revises: 0090
Create Date: 2026-09-08

"""
from alembic import op
import sqlalchemy as sa


revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_coach_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.Enum("club_pack", name="club_coach_card_source_enum"), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_coach_cards_club_id", "club_coach_cards", ["club_id"])
    op.create_index("ix_club_coach_cards_coach_id", "club_coach_cards", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_club_coach_cards_coach_id", table_name="club_coach_cards")
    op.drop_index("ix_club_coach_cards_club_id", table_name="club_coach_cards")
    op.drop_table("club_coach_cards")
    bind = op.get_bind()
    sa.Enum(name="club_coach_card_source_enum").drop(bind, checkfirst=True)
