"""Collectible gift editions: serial numbers, max supply, collection tag

Revision ID: 0053
Revises: 0052
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gift_sets", sa.Column("max_supply", sa.Integer(), nullable=True))
    op.add_column("gift_sets", sa.Column("next_serial_number", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "gift_sets",
        sa.Column("collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("gifts", sa.Column("serial_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("gifts", "serial_number")
    op.drop_column("gift_sets", "collection_id")
    op.drop_column("gift_sets", "next_serial_number")
    op.drop_column("gift_sets", "max_supply")
