"""Add Pack.coach_drop_chance and make PackOpeningCard a player-XOR-coach row

Revision ID: 0097
Revises: 0096
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0097"
down_revision: Union[str, None] = "0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "packs",
        sa.Column("coach_drop_chance", sa.Numeric(5, 4), nullable=False, server_default="0"),
    )

    op.add_column("pack_opening_cards", sa.Column("user_coach_card_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_pack_opening_cards_user_coach_card_id", "pack_opening_cards",
        "user_coach_cards", ["user_coach_card_id"], ["id"], ondelete="CASCADE",
    )

    op.alter_column("pack_opening_cards", "user_card_id", nullable=True)
    op.alter_column("pack_opening_cards", "is_new_player", new_column_name="is_new")

    op.create_check_constraint(
        "ck_pack_opening_card_exactly_one_kind",
        "pack_opening_cards",
        "(user_card_id IS NOT NULL AND user_coach_card_id IS NULL) OR "
        "(user_card_id IS NULL AND user_coach_card_id IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_pack_opening_card_exactly_one_kind", "pack_opening_cards", type_="check")
    op.alter_column("pack_opening_cards", "is_new", new_column_name="is_new_player")
    op.alter_column("pack_opening_cards", "user_card_id", nullable=False)
    op.drop_constraint("fk_pack_opening_cards_user_coach_card_id", "pack_opening_cards", type_="foreignkey")
    op.drop_column("pack_opening_cards", "user_coach_card_id")
    op.drop_column("packs", "coach_drop_chance")
