"""Collectible gifts: kind discriminator, coin pricing, pinning

Revision ID: 0052
Revises: 0051
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0052"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

gift_kind_enum = postgresql.ENUM("bundle", "collectible", name="gift_kind_enum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    gift_kind_enum.create(bind, checkfirst=True)

    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'gift_purchase_coins'")

    op.add_column("gift_sets", sa.Column("kind", gift_kind_enum, nullable=False, server_default="bundle"))
    op.add_column("gift_sets", sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("gifts", sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("gifts", sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("gifts", "pinned_at")
    op.drop_column("gifts", "is_pinned")
    op.drop_column("gift_sets", "coins_price")
    op.drop_column("gift_sets", "kind")
    op.execute("DROP TYPE IF EXISTS gift_kind_enum")
