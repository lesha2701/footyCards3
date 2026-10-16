"""stars_payment_receipts: durable record of every Stars payment received

Revision ID: 0153
Revises: 0152
Create Date: 2026-10-16

Telegram charges the player before we deliver the purchase. Until now a
failed delivery only left a log line; this table records every
successful_payment (written by the bot before it asks the backend to
deliver) so failed deliveries are retried automatically and can be
re-delivered or refunded from the admin panel.

created_at/updated_at get server defaults because the bot inserts rows with
raw SQL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0153"
down_revision: Union[str, None] = "0152"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "stars_payment_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_payment_charge_id", sa.String(255), nullable=False),
        sa.Column("payload_token", sa.String(64), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("total_amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("telegram_payment_charge_id", name="uq_stars_payment_receipts_charge_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'delivered', 'failed', 'refunded')", name="ck_stars_payment_receipts_status"
        ),
    )
    op.create_index("ix_stars_payment_receipts_payload_token", "stars_payment_receipts", ["payload_token"])
    op.create_index("ix_stars_payment_receipts_telegram_user_id", "stars_payment_receipts", ["telegram_user_id"])
    op.create_index("ix_stars_payment_receipts_retry", "stars_payment_receipts", ["status", "next_attempt_at"])

    # Payments already delivered before this table existed: record them as
    # delivered, so the admin history is complete and nothing is retried.
    op.execute(
        """
        INSERT INTO stars_payment_receipts
            (telegram_payment_charge_id, payload_token, telegram_user_id, total_amount,
             status, attempts, delivered_at, created_at, updated_at)
        SELECT i.telegram_payment_charge_id, i.payload_token, u.telegram_id, i.stars_amount,
               'delivered', 1, i.completed_at, i.completed_at, i.completed_at
        FROM stars_invoices i JOIN users u ON u.id = i.user_id
        WHERE i.completed_at IS NOT NULL AND i.telegram_payment_charge_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_stars_payment_receipts_retry", table_name="stars_payment_receipts")
    op.drop_index("ix_stars_payment_receipts_telegram_user_id", table_name="stars_payment_receipts")
    op.drop_index("ix_stars_payment_receipts_payload_token", table_name="stars_payment_receipts")
    op.drop_table("stars_payment_receipts")
