"""Buy coins with Telegram Stars: configurable rate/bulk bonus, and let a
stars_invoices row represent either a pack purchase or a coin top-up.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'stars_coin_purchase'")

    op.add_column("game_config", sa.Column("stars_to_coins_rate", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("stars_bulk_threshold", sa.Integer(), nullable=False, server_default="50"))
    op.add_column(
        "game_config", sa.Column("stars_bulk_bonus_pct", sa.Numeric(4, 2), nullable=False, server_default="0.10")
    )

    op.alter_column("stars_invoices", "pack_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("stars_invoices", sa.Column("coins_amount", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("stars_invoices", "coins_amount")
    op.alter_column("stars_invoices", "pack_id", existing_type=sa.Integer(), nullable=False)

    op.drop_column("game_config", "stars_bulk_bonus_pct")
    op.drop_column("game_config", "stars_bulk_threshold")
    op.drop_column("game_config", "stars_to_coins_rate")
