"""«Карты за звёзды» reminder: card_offer_views (who opened the tab while an
offer was on sale) and card_offers.reminded_at (the «осталось 3 часа»
message went out, once per offer).

Revision ID: 0203
Revises: 0202
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0203"
down_revision: Union[str, None] = "0202"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("card_offers", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "card_offer_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("offer_id", sa.Integer(), sa.ForeignKey("card_offers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("offer_id", "user_id", name="uq_card_offer_views_offer_user"),
    )
    op.create_index("ix_card_offer_views_offer_id", "card_offer_views", ["offer_id"])


def downgrade() -> None:
    op.drop_index("ix_card_offer_views_offer_id", table_name="card_offer_views")
    op.drop_table("card_offer_views")
    op.drop_column("card_offers", "reminded_at")
