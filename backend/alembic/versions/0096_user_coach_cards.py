"""Add UserCoachCard — personal (non-club) coach ownership

Revision ID: 0096
Revises: 0095
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0096"
down_revision: Union[str, None] = "0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    card_source_enum = postgresql.ENUM(
        "pack", "daily_reward", "trade", "admin_grant", "achievement", "game_reward", "seed", "task",
        "free_pack", "card_upgrade", "collection_reward", "stars_purchase", "chat_pack", "gift", "wheel",
        "league_reward", name="card_source_enum", create_type=False,
    )

    op.create_table(
        "user_coach_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id"), nullable=False),
        sa.Column("serial_number", sa.Integer(), nullable=False),
        sa.Column("source", card_source_enum, nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_coach_cards_user_id", "user_coach_cards", ["user_id"])
    op.create_index("ix_user_coach_cards_coach_id", "user_coach_cards", ["coach_id"])


def downgrade() -> None:
    op.drop_index("ix_user_coach_cards_coach_id", table_name="user_coach_cards")
    op.drop_index("ix_user_coach_cards_user_id", table_name="user_coach_cards")
    op.drop_table("user_coach_cards")
