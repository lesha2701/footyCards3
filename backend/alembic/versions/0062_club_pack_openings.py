"""ClubPackOpening/ClubPackOpeningCard: club pack purchase history

Revision ID: 0062
Revises: 0061
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_pack_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_pack_id", sa.Integer(), sa.ForeignKey("club_packs.id"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_pack_openings_club_id", "club_pack_openings", ["club_id"])
    op.create_unique_constraint("uq_club_pack_opening_idempotency", "club_pack_openings", ["club_id", "idempotency_key"])

    op.create_table(
        "club_pack_opening_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opening_id", sa.Integer(), sa.ForeignKey("club_pack_openings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_card_id", sa.Integer(), sa.ForeignKey("club_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_player", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_club_pack_opening_cards_opening_id", "club_pack_opening_cards", ["opening_id"])


def downgrade() -> None:
    op.drop_table("club_pack_opening_cards")
    op.drop_table("club_pack_openings")
