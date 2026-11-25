"""Gift collectors: gift_transfers (batches + a copy's history), gifts.transfer_unseen

Revision ID: 0339
Revises: 0338
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0339"
down_revision: Union[str, None] = "0338"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("gifts", sa.Column("transfer_unseen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "gift_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch", sa.String(32), nullable=False),
        sa.Column("gift_id", sa.Integer(), sa.ForeignKey("gifts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prev_sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("message", sa.String(500), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_gift_transfers_batch", "gift_transfers", ["batch"])
    op.create_index("ix_gift_transfers_gift_id", "gift_transfers", ["gift_id"])


def downgrade() -> None:
    op.drop_index("ix_gift_transfers_gift_id", table_name="gift_transfers")
    op.drop_index("ix_gift_transfers_batch", table_name="gift_transfers")
    op.drop_table("gift_transfers")
    op.drop_column("gifts", "transfer_unseen")
