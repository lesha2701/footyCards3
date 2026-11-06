"""Card Arena live layer: decisions tuning, timers, weekend cup, defense log
and per-card Arena stats.

Revision ID: 0261
Revises: 0260
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0261"
down_revision: Union[str, None] = "0260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'arena_cup_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'arena_goal_bonus'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'arena_defense'")

    for name, default in (
        ("arena_moment_seconds", "8"), ("arena_auto_best_pct", "60"), ("arena_abandon_minutes", "20"),
        ("arena_hint_accuracy_pct", "70"), ("arena_goal_bonus_coins", "15"),
    ):
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("arena_cup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in (
        ("arena_decision_tuning", "{}"), ("arena_cup_weekdays", "[5, 6]"),
        ("arena_cup_round_rewards", "[100, 200, 400, 800]"), ("arena_cup_round_strength_pct", "[95, 100, 106, 112]"),
    ):
        op.add_column("game_config", sa.Column(name, sa.JSON(), nullable=False, server_default=default))

    op.add_column("users", sa.Column("arena_defense_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("arena_defense_notified_at", sa.DateTime(timezone=True), nullable=True))
    for name in ("arena_goals", "arena_assists", "arena_mvps"):
        op.add_column("user_cards", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))

    op.create_index("ix_matches_opponent_user_id", "matches", ["opponent_user_id"])
    op.create_table(
        "arena_cup_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_key", sa.String(16), nullable=False),
        sa.Column("rounds_won", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week_key", name="uq_arena_cup_runs_user_week"),
    )
    op.create_index("ix_arena_cup_runs_user_id", "arena_cup_runs", ["user_id"])
    op.create_index("ix_arena_cup_runs_week_key", "arena_cup_runs", ["week_key"])


def downgrade() -> None:
    op.drop_table("arena_cup_runs")
    op.drop_index("ix_matches_opponent_user_id", table_name="matches")
    for name in ("arena_goals", "arena_assists", "arena_mvps"):
        op.drop_column("user_cards", name)
    op.drop_column("users", "arena_defense_notified_at")
    op.drop_column("users", "arena_defense_seen_at")
    for name in (
        "arena_moment_seconds", "arena_auto_best_pct", "arena_abandon_minutes", "arena_hint_accuracy_pct",
        "arena_goal_bonus_coins", "arena_cup_enabled", "arena_decision_tuning", "arena_cup_weekdays",
        "arena_cup_round_rewards", "arena_cup_round_strength_pct",
    ):
        op.drop_column("game_config", name)
