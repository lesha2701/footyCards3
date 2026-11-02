"""«Музы»: a footballers' card collection they count toward, and «лимитка».

- muses.card_collection_id: the card collection (like stadiums / coaches)
  the Muse counts toward together with its footballers.
- muses.is_pack_droppable: false = «лимитка», never drops from packs (only
  Stars offers, the admin grant, events).

Revision ID: 0240
Revises: 0239
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0240"
down_revision: Union[str, None] = "0239"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("muses", sa.Column(
        "card_collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_muses_card_collection_id", "muses", ["card_collection_id"])
    op.add_column("muses", sa.Column("is_pack_droppable", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("muses", "is_pack_droppable")
    op.drop_index("ix_muses_card_collection_id", table_name="muses")
    op.drop_column("muses", "card_collection_id")
