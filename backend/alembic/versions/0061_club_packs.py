"""ClubPack + ClubPackRarityProbability: club-only pack list

Revision ID: 0061
Revises: 0060
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# rarity_enum was already created in 0001_initial; reuse it rather than
# re-declaring (which would try to CREATE TYPE again and fail).
rarity_enum = postgresql.ENUM("common", "rare", "epic", "legendary", name="rarity_enum", create_type=False)


def upgrade() -> None:
    op.create_table(
        "club_packs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("card_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("guaranteed_min_rarity", rarity_enum, nullable=True),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_pack_rarity_probabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_pack_id", sa.Integer(), sa.ForeignKey("club_packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rarity", rarity_enum, nullable=False),
        sa.Column("probability", sa.Numeric(6, 4), nullable=False),
    )
    op.create_unique_constraint(
        "uq_club_pack_rarity_once", "club_pack_rarity_probabilities", ["club_pack_id", "rarity"]
    )


def downgrade() -> None:
    op.drop_table("club_pack_rarity_probabilities")
    op.drop_table("club_packs")
