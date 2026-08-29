"""Add the "Что исчезло?" club mini-game

Revision ID: 0081
Revises: 0080
Create Date: 2026-08-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0081"
down_revision: Union[str, None] = "0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'club_missing_item'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'club_missing_item_reward'")

    op.add_column("users", sa.Column("club_missing_item_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_missing_item_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_missing_item_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_missing_item_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_missing_item_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_missing_item_reward_cap", sa.Integer(), nullable=False, server_default="100"))

    op.create_table(
        "missing_item_rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("items", sa.String(length=256), nullable=False),
        sa.Column("removed_item", sa.String(length=16), nullable=True),
        sa.Column("was_correct", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("missing_item_rounds")

    op.drop_column("game_config", "club_missing_item_reward_cap")
    op.drop_column("game_config", "club_missing_item_daily_reward_limit")
    op.drop_column("game_config", "club_missing_item_hourly_limit")

    op.drop_column("users", "club_missing_item_hour_started_at")
    op.drop_column("users", "club_missing_item_hourly_attempts")
    op.drop_column("users", "club_missing_item_attempts_reset_at")
    op.drop_column("users", "club_missing_item_rewarded_attempts_today")

    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
