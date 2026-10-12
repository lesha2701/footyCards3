"""«Футбольное Стратего»: match + matchmaking queue tables, per-user hourly /
daily limit counters and saved squad, GameConfig settings, notification and
transaction types.

Revision ID: 0135
Revises: 0134
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0135"
down_revision: Union[str, None] = "0134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

stratego_opponent_type_enum = postgresql.ENUM(
    "bot", "friend", "online", "chat", name="stratego_opponent_type_enum", create_type=False,
)
stratego_match_status_enum = postgresql.ENUM(
    "pending_accept", "in_progress", "finished", "declined", "cancelled", "expired",
    name="stratego_match_status_enum", create_type=False,
)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)

NEW_ENUMS = [stratego_opponent_type_enum, stratego_match_status_enum]

CONFIG_INT_COLUMNS = (
    ("stratego_board_size", "8"),
    ("stratego_wall_count", "2"),
    ("stratego_tackler_count", "3"),
    ("stratego_speedster_count", "2"),
    ("stratego_regular_count", "6"),
    ("stratego_move_limit", "300"),
    ("stratego_max_legendary_cards", "3"),
    ("stratego_max_diamond_cards", "1"),
    ("stratego_min_rare_cards", "4"),
    ("stratego_min_common_cards", "2"),
    ("stratego_my_player_xp", "15"),
    ("stratego_bot_easy_reward_pct", "60"),
    ("stratego_live_move_seconds", "60"),
    ("stratego_skill_bonus_per_level", "2"),
    ("stratego_puzzle_reward", "50"),
    ("stratego_challenge_expiry_hours", "24"),
    ("stratego_move_timeout_hours", "12"),
    ("stratego_max_auto_moves", "3"),
    ("stratego_reward_win", "100"),
    ("stratego_reward_draw", "50"),
    ("stratego_reward_loss", "50"),
    ("stratego_daily_limit", "10"),
)


def upgrade() -> None:
    for value in ("stratego_reward", "stratego_stake_lock", "stratego_stake_win", "stratego_stake_refund"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    for value in (
        "stratego_challenge_received", "stratego_challenge_accepted",
        "stratego_your_turn", "stratego_match_finished",
    ):
        op.execute(f"ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "stratego_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("opponent_type", stratego_opponent_type_enum, nullable=False),
        sa.Column("status", stratego_match_status_enum, nullable=False, server_default="pending_accept"),
        sa.Column("result", match_result_enum, nullable=True),
        sa.Column("mode", sa.String(16), nullable=False, server_default="normal"),
        sa.Column("win_reason", sa.String(32), nullable=True),
        sa.Column("user_reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stake_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_state", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_stratego_matches_user_id", "stratego_matches", ["user_id"])
    op.create_index("ix_stratego_matches_opponent_user_id", "stratego_matches", ["opponent_user_id"])
    op.create_index("ix_stratego_matches_status", "stratego_matches", ["status"])
    op.create_index("ix_stratego_matches_created_at", "stratego_matches", ["created_at"])

    op.create_table(
        "stratego_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("stratego_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_stratego_queue_entries_user_id", "stratego_queue_entries", ["user_id"], unique=True)

    op.add_column("users", sa.Column("stratego_rating", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("stratego_puzzle_day", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("stratego_puzzles_solved", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("stratego_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("stratego_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("stratego_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("stratego_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("stratego_squad", sa.JSON(), nullable=True))

    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column(
        "game_config", sa.Column("stratego_tackler_max_rarity", sa.String(16), nullable=False, server_default="epic"),
    )


def downgrade() -> None:
    op.drop_column("game_config", "stratego_tackler_max_rarity")
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    for name in (
        "stratego_squad", "stratego_hour_started_at", "stratego_hourly_attempts",
        "stratego_attempts_reset_at", "stratego_rewarded_attempts_today", "stratego_rating",
        "stratego_puzzle_day", "stratego_puzzles_solved",
    ):
        op.drop_column("users", name)
    op.drop_index("ix_stratego_queue_entries_user_id", table_name="stratego_queue_entries")
    op.drop_table("stratego_queue_entries")
    for index in (
        "ix_stratego_matches_created_at", "ix_stratego_matches_status",
        "ix_stratego_matches_opponent_user_id", "ix_stratego_matches_user_id",
    ):
        op.drop_index(index, table_name="stratego_matches")
    op.drop_table("stratego_matches")
    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
    # Postgres cannot drop individual enum values — the added
    # notification/transaction type values stay (same as earlier migrations).
