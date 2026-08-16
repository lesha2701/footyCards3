"""Penalty matchmaking: queue table + opponent type

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

penalty_opponent_type_enum = postgresql.ENUM(
    "friend", "online", name="penalty_opponent_type_enum", create_type=False
)


def upgrade() -> None:
    penalty_opponent_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "penalty_matches",
        sa.Column("opponent_type", penalty_opponent_type_enum, nullable=False, server_default="friend"),
    )

    op.create_table(
        "penalty_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("penalty_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_unique_constraint("uq_penalty_queue_entries_user_id", "penalty_queue_entries", ["user_id"])
    op.create_index("ix_penalty_queue_entries_user_id", "penalty_queue_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_penalty_queue_entries_user_id", table_name="penalty_queue_entries")
    op.drop_table("penalty_queue_entries")
    op.drop_column("penalty_matches", "opponent_type")
    penalty_opponent_type_enum.drop(op.get_bind(), checkfirst=True)
