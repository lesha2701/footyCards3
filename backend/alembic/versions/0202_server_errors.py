"""server_errors: unhandled exceptions (500s) for the admins' daily digest
from the bot (error_log_service, bot/services/watchdog.py).

Revision ID: 0202
Revises: 0201
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0202"
down_revision: Union[str, None] = "0201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "server_errors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("error", sa.String(255), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_server_errors_created_at", "server_errors", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_server_errors_created_at", table_name="server_errors")
    op.drop_table("server_errors")
