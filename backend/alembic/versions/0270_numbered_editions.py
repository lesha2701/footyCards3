"""Numbered card editions («№37 из 100»): players.edition_size, and
card_offer_reservations — a copy held for an invoice between pre-checkout and
delivery, so a limited offer can't be sold past its stock.

Revision ID: 0270
Revises: 0269
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0270"
down_revision: Union[str, None] = "0269"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("edition_size", sa.Integer(), nullable=True))
    op.create_table(
        "card_offer_reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("card_offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("stars_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("invoice_id", name="uq_card_offer_reservations_invoice"),
    )
    op.create_index("ix_card_offer_reservations_offer_id", "card_offer_reservations", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_card_offer_reservations_offer_id", table_name="card_offer_reservations")
    op.drop_table("card_offer_reservations")
    op.drop_column("players", "edition_size")
