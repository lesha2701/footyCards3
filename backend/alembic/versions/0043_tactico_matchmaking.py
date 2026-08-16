"""Tactico matchmaking: queue table + online opponent type

Revision ID: 0043
Revises: 0042
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tactico_opponent_type_enum ADD VALUE IF NOT EXISTS 'online'")

    op.create_table(
        "tactico_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("tactico_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_unique_constraint("uq_tactico_queue_entries_user_id", "tactico_queue_entries", ["user_id"])
    op.create_index("ix_tactico_queue_entries_user_id", "tactico_queue_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_tactico_queue_entries_user_id", table_name="tactico_queue_entries")
    op.drop_table("tactico_queue_entries")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'online' on the enum
    # on downgrade is harmless (mirrors every prior migration's same note).
