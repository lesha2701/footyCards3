"""Widen stars_invoices.telegram_payment_charge_id — real Telegram Stars
charge ids observed in production run past 128 characters.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "stars_invoices", "telegram_payment_charge_id",
        existing_type=sa.String(length=128), type_=sa.String(length=255), existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "stars_invoices", "telegram_payment_charge_id",
        existing_type=sa.String(length=255), type_=sa.String(length=128), existing_nullable=True,
    )
