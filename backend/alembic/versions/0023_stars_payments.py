"""Telegram Stars payments: stars-only packs + invoice tracking table

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'stars_purchase'")

    op.add_column("packs", sa.Column("stars_price", sa.Integer(), nullable=True))

    op.create_table(
        "stars_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload_token", sa.String(length=64), nullable=False, unique=True),
        sa.Column("stars_amount", sa.Integer(), nullable=False),
        sa.Column("telegram_payment_charge_id", sa.String(length=128), nullable=True, unique=True),
        sa.Column(
            "pack_opening_id", sa.Integer(), sa.ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_stars_invoices_user_id", "stars_invoices", ["user_id"])
    op.create_index("ix_stars_invoices_payload_token", "stars_invoices", ["payload_token"])


def downgrade() -> None:
    op.drop_index("ix_stars_invoices_payload_token", table_name="stars_invoices")
    op.drop_index("ix_stars_invoices_user_id", table_name="stars_invoices")
    op.drop_table("stars_invoices")
    op.drop_column("packs", "stars_price")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'stars_purchase' on
    # the enum on downgrade is harmless (mirrors 0009's football_hangman note).
