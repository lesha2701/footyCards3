"""Add Club Sequence mini-game: User columns, GameConfig columns, and
game_type_enum / club_budget_transaction_type_enum values.

Revision ID: 0074
Revises: 0073
Create Date: 2026-08-28
"""
import sqlalchemy as sa
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'club_sequence'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'club_game_reward'")

    op.add_column("users", sa.Column("club_game_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_game_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_game_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_game_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("club_game_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_game_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_game_reward_cap", sa.Integer(), nullable=False, server_default="100"))


def downgrade() -> None:
    op.drop_column("game_config", "club_game_reward_cap")
    op.drop_column("game_config", "club_game_daily_reward_limit")
    op.drop_column("game_config", "club_game_hourly_limit")

    op.drop_column("users", "club_game_hour_started_at")
    op.drop_column("users", "club_game_hourly_attempts")
    op.drop_column("users", "club_game_attempts_reset_at")
    op.drop_column("users", "club_game_rewarded_attempts_today")

    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
