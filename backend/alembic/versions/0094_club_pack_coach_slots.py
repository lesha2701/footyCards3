"""Add ClubPack.coach_drop_chance and make ClubPackOpeningCard a
player-XOR-coach row

Revision ID: 0094
Revises: 0093
Create Date: 2026-09-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "club_packs",
        sa.Column("coach_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )

    op.add_column("club_pack_opening_cards", sa.Column("club_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_club_pack_opening_cards_club_coach_card_id", "club_pack_opening_cards",
        "club_coach_cards", ["club_coach_card_id"], ["id"], ondelete="CASCADE",
    )

    op.alter_column("club_pack_opening_cards", "club_card_id", nullable=True)
    op.alter_column("club_pack_opening_cards", "is_new_player", new_column_name="is_new")

    op.create_check_constraint(
        "ck_club_pack_opening_card_exactly_one_kind",
        "club_pack_opening_cards",
        "(club_card_id IS NOT NULL AND club_coach_card_id IS NULL) OR "
        "(club_card_id IS NULL AND club_coach_card_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_club_pack_opening_card_exactly_one_kind", "club_pack_opening_cards", type_="check")
    op.alter_column("club_pack_opening_cards", "is_new", new_column_name="is_new_player")
    op.alter_column("club_pack_opening_cards", "club_card_id", nullable=False)
    op.drop_constraint("fk_club_pack_opening_cards_club_coach_card_id", "club_pack_opening_cards", type_="foreignkey")
    op.drop_column("club_pack_opening_cards", "club_coach_card_id")
    op.drop_column("club_packs", "coach_drop_chance")
