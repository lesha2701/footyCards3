"""Gift system: admin-curated gift sets, player-to-player and admin gifting

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'gift'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'gift_coins'")

    op.create_table(
        "gift_sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=False, server_default=""),
        sa.Column("image_path", sa.String(length=255), nullable=True),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("coins_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("gift_set_id", sa.Integer(), sa.ForeignKey("gift_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("is_admin_gift", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pack_opening_id", sa.Integer(), sa.ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_gifts_gift_set_id", "gifts", ["gift_set_id"])
    op.create_index("ix_gifts_recipient_id", "gifts", ["recipient_id"])

    op.add_column("stars_invoices", sa.Column("gift_set_id", sa.Integer(), sa.ForeignKey("gift_sets.id", ondelete="CASCADE"), nullable=True))
    op.add_column("stars_invoices", sa.Column("gift_recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
    op.add_column("stars_invoices", sa.Column("gift_message", sa.String(length=500), nullable=True))
    op.add_column("stars_invoices", sa.Column("gift_id", sa.Integer(), sa.ForeignKey("gifts.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("stars_invoices", "gift_id")
    op.drop_column("stars_invoices", "gift_message")
    op.drop_column("stars_invoices", "gift_recipient_id")
    op.drop_column("stars_invoices", "gift_set_id")

    op.drop_index("ix_gifts_recipient_id", table_name="gifts")
    op.drop_index("ix_gifts_gift_set_id", table_name="gifts")
    op.drop_table("gifts")
    op.drop_table("gift_sets")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'gift'/'gift_coins'
    # on their enums on downgrade is harmless (mirrors 0029's note).
