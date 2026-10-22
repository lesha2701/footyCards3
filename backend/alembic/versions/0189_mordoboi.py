"""«Мордобой»: match + matchmaking queue tables, per-user rating / hourly /
daily counters and saved boxer, GameConfig settings (off by default),
notification and transaction types.

Revision ID: 0189
Revises: 0188
Create Date: 2026-10-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0189"
down_revision: Union[str, None] = "0188"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

mordoboi_opponent_type_enum = postgresql.ENUM(
    "bot", "friend", "online", name="mordoboi_opponent_type_enum", create_type=False,
)
mordoboi_match_status_enum = postgresql.ENUM(
    "pending_accept", "in_progress", "finished", "declined", "cancelled", "expired",
    name="mordoboi_match_status_enum", create_type=False,
)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)

NEW_ENUMS = [mordoboi_opponent_type_enum, mordoboi_match_status_enum]

CONFIG_INT_COLUMNS = (
    ("mordoboi_rounds", "3"),
    ("mordoboi_exchanges_per_round", "4"),
    ("mordoboi_base_hp", "100"),
    ("mordoboi_reward_win", "80"),
    ("mordoboi_reward_draw", "40"),
    ("mordoboi_reward_loss", "25"),
    ("mordoboi_reward_ko_bonus", "20"),
    ("mordoboi_daily_limit", "10"),
    ("mordoboi_bot_easy_reward_pct", "60"),
    ("mordoboi_challenge_expiry_hours", "24"),
    ("mordoboi_move_timeout_hours", "12"),
    ("mordoboi_live_move_seconds", "30"),
    ("mordoboi_max_auto_moves", "3"),
)

USER_COLUMNS = (
    "mordoboi_rating", "mordoboi_rewarded_attempts_today", "mordoboi_attempts_reset_at",
    "mordoboi_hourly_attempts", "mordoboi_hour_started_at", "mordoboi_card_id",
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'mordoboi_reward'")
    for value in (
        "mordoboi_challenge_received", "mordoboi_challenge_accepted",
        "mordoboi_your_turn", "mordoboi_match_finished",
    ):
        op.execute(f"ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "mordoboi_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("opponent_type", mordoboi_opponent_type_enum, nullable=False),
        sa.Column("status", mordoboi_match_status_enum, nullable=False, server_default="pending_accept"),
        sa.Column("result", match_result_enum, nullable=True),
        sa.Column("win_reason", sa.String(32), nullable=True),
        sa.Column("user_reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("server_state", sa.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mordoboi_matches_user_id", "mordoboi_matches", ["user_id"])
    op.create_index("ix_mordoboi_matches_opponent_user_id", "mordoboi_matches", ["opponent_user_id"])
    op.create_index("ix_mordoboi_matches_status", "mordoboi_matches", ["status"])
    op.create_index("ix_mordoboi_matches_created_at", "mordoboi_matches", ["created_at"])

    op.create_table(
        "mordoboi_queue_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "matched_match_id", sa.Integer(),
            sa.ForeignKey("mordoboi_matches.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_mordoboi_queue_entries_user_id", "mordoboi_queue_entries", ["user_id"], unique=True)

    op.add_column("users", sa.Column("mordoboi_rating", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mordoboi_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mordoboi_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mordoboi_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("mordoboi_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mordoboi_card_id", sa.Integer(), nullable=True))

    op.add_column("game_config", sa.Column("mordoboi_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "mordoboi_enabled")
    for name in reversed(USER_COLUMNS):
        op.drop_column("users", name)
    op.drop_index("ix_mordoboi_queue_entries_user_id", table_name="mordoboi_queue_entries")
    op.drop_table("mordoboi_queue_entries")
    for index in (
        "ix_mordoboi_matches_created_at", "ix_mordoboi_matches_status",
        "ix_mordoboi_matches_opponent_user_id", "ix_mordoboi_matches_user_id",
    ):
        op.drop_index(index, table_name="mordoboi_matches")
    op.drop_table("mordoboi_matches")
    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
    # Postgres cannot drop individual enum values — the added
    # notification/transaction type values stay (same as earlier migrations).
