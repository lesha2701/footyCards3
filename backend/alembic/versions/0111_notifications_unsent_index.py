"""Partial index on notifications for the unsent-delivery-queue scan.

The bot's dispatcher (bot/services/notifier.py) repeatedly runs
SELECT ... FROM notifications WHERE telegram_sent = false ORDER BY id LIMIT N
to find what to deliver next. Sent rows are never deleted, so without an
index on telegram_sent this scan gets slower as the table grows, even
though the number of *unsent* rows at any moment stays small. A partial
index — only rows where telegram_sent = false — stays small for the same
reason and serves this exact query (WHERE + ORDER BY on the same column set).

Revision ID: 0111
Revises: 0110
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0111"
down_revision: Union[str, None] = "0110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notifications_unsent ON notifications (id) WHERE telegram_sent = false"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notifications_unsent")
