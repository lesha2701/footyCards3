"""ClubLineup/ClubLineupCard: fixed 4-3-3 squad for a club

Revision ID: 0059
Revises: 0058
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0059"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_lineups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "club_lineup_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_lineup_id", sa.Integer(), sa.ForeignKey("club_lineups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot_code", sa.String(length=16), nullable=False),
    )
    op.create_index("ix_club_lineup_cards_club_lineup_id", "club_lineup_cards", ["club_lineup_id"])
    op.create_index("ix_club_lineup_cards_club_card_id", "club_lineup_cards", ["club_card_id"])
    op.create_unique_constraint("uq_club_lineup_card_once", "club_lineup_cards", ["club_lineup_id", "club_card_id"])
    op.create_unique_constraint("uq_club_lineup_slot_once", "club_lineup_cards", ["club_lineup_id", "slot_code"])


def downgrade() -> None:
    op.drop_table("club_lineup_cards")
    op.drop_table("club_lineups")
