"""Move Своя позиция into the club games; share one hourly play pool across
all club mini-games instead of a separate hourly limit per game.

Revision ID: 0108
Revises: 0107
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0108"
down_revision: Union[str, None] = "0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'club_position_match'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'club_position_match_reward'")

    # Retire the personal "Своя позиция" surface — moved into the club games.
    op.drop_column("users", "position_match_rewarded_attempts_today")
    op.drop_column("users", "position_match_attempts_reset_at")
    op.drop_column("users", "position_match_hourly_attempts")
    op.drop_column("users", "position_match_hour_started_at")
    op.drop_column("game_config", "position_match_daily_limit")
    op.drop_column("game_config", "position_match_max_mistakes")
    op.drop_column("game_config", "position_match_reward_perfect")
    op.drop_column("game_config", "position_match_reward_min")
    op.drop_column("game_config", "position_match_penalty_per_mistake")

    # Replace the two independent per-game hourly counters with one shared pool.
    op.drop_column("users", "club_game_hourly_attempts")
    op.drop_column("users", "club_game_hour_started_at")
    op.drop_column("users", "club_penalty_hourly_attempts")
    op.drop_column("users", "club_penalty_hour_started_at")
    op.drop_column("game_config", "club_game_hourly_limit")
    op.drop_column("game_config", "club_penalty_hourly_limit")

    op.add_column("users", sa.Column("club_games_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_games_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("club_games_hourly_limit", sa.Integer(), nullable=False, server_default="2"))

    # New club-scoped "Своя позиция" — daily reward cap only, hourly play
    # comes out of the shared pool above.
    op.add_column("users", sa.Column("club_position_match_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_position_match_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("club_position_match_daily_reward_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("club_position_match_max_mistakes", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("club_position_match_reward_perfect", sa.Integer(), nullable=False, server_default="35"))
    op.add_column("game_config", sa.Column("club_position_match_reward_min", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("club_position_match_penalty_per_mistake", sa.Integer(), nullable=False, server_default="8"))


def downgrade() -> None:
    op.drop_column("game_config", "club_position_match_penalty_per_mistake")
    op.drop_column("game_config", "club_position_match_reward_min")
    op.drop_column("game_config", "club_position_match_reward_perfect")
    op.drop_column("game_config", "club_position_match_max_mistakes")
    op.drop_column("game_config", "club_position_match_daily_reward_limit")
    op.drop_column("users", "club_position_match_attempts_reset_at")
    op.drop_column("users", "club_position_match_rewarded_attempts_today")

    op.drop_column("game_config", "club_games_hourly_limit")
    op.drop_column("users", "club_games_hour_started_at")
    op.drop_column("users", "club_games_hourly_attempts")

    op.add_column("game_config", sa.Column("club_penalty_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("club_game_hourly_limit", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("users", sa.Column("club_penalty_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_penalty_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("club_game_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("club_game_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("game_config", sa.Column("position_match_penalty_per_mistake", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("position_match_reward_min", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("position_match_reward_perfect", sa.Integer(), nullable=False, server_default="35"))
    op.add_column("game_config", sa.Column("position_match_max_mistakes", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("position_match_daily_limit", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("users", sa.Column("position_match_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("position_match_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("position_match_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("position_match_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))

    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'club_position_match'
    # (GameType) and 'club_position_match_reward' (ClubBudgetTransactionType)
    # on their enums is harmless (mirrors 0030's card_pairs note).
