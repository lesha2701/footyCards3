"""Drop the ClubCoachPack/ClubCoachPackOpening tables — coaches now drop
from ClubPack directly (see 0094)

Revision ID: 0095
Revises: 0094
Create Date: 2026-09-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

rarity_enum = postgresql.ENUM(
    "common", "rare", "epic", "legendary", "diamond", name="rarity_enum", create_type=False
)


def upgrade() -> None:
    op.drop_table("club_coach_pack_opening_cards")
    op.drop_table("club_coach_pack_openings")
    op.drop_table("club_coach_pack_rarity_probabilities")
    op.drop_table("club_coach_packs")


def downgrade() -> None:
    # Recreates the 4 tables dropped above, mirroring 0092_club_coach_packs.py's own
    # upgrade() exactly (same columns, constraints and indexes, in the same dependency
    # order) so this migration round-trips cleanly instead of being a dead end.
    op.create_table(
        "club_coach_packs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("guaranteed_min_rarity", rarity_enum, nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_coach_pack_rarity_probabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_coach_pack_id", sa.Integer(), sa.ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("probability", sa.Numeric(6, 4), nullable=False),
    )
    op.create_unique_constraint(
        "uq_club_coach_pack_rarity_once", "club_coach_pack_rarity_probabilities", ["club_coach_pack_id", "rarity"]
    )

    op.create_table(
        "club_coach_pack_openings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_coach_pack_id", sa.Integer(), sa.ForeignKey("club_coach_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opened_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("price_paid", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_coach_pack_openings_club_id", "club_coach_pack_openings", ["club_id"])
    op.create_unique_constraint(
        "uq_club_coach_pack_opening_idempotency", "club_coach_pack_openings", ["club_id", "idempotency_key"]
    )
    op.create_table(
        "club_coach_pack_opening_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("opening_id", sa.Integer(), sa.ForeignKey("club_coach_pack_openings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_coach_card_id", sa.Integer(), sa.ForeignKey("club_coach_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_coach", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_club_coach_pack_opening_cards_opening_id", "club_coach_pack_opening_cards", ["opening_id"])
