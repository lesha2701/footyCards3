"""«Футбольный магнат»: match + seat tables, per-user limit counters and
wins, GameConfig settings, magnate_reward transaction type.

Revision ID: 0136
Revises: 0135
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0136"
down_revision: Union[str, None] = "0135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("magnate_start_money", "1500"),
    ("magnate_pass_start_bonus", "200"),
    ("magnate_jail_fine", "50"),
    ("magnate_max_jail_turns", "3"),
    ("magnate_fine_amount", "100"),
    ("magnate_building_sell_pct", "50"),
    ("magnate_max_rounds", "20"),
    ("magnate_time_limit_minutes", "30"),
    ("magnate_turn_seconds", "30"),
    ("magnate_max_missed_turns", "2"),
    ("magnate_lobby_wait_seconds", "45"),
    ("magnate_room_wait_minutes", "10"),
    ("magnate_bot_buy_reserve", "150"),
    ("magnate_bot_build_reserve", "250"),
    ("magnate_bot_reward_pct", "70"),
    ("magnate_daily_limit", "5"),
)
CONFIG_JSON_COLUMNS = (
    ("magnate_place_rewards", "[150, 75, 35, 10]"),
    ("magnate_stadium_rents", "[25, 50, 100, 200]"),
)
USER_COLUMNS = (
    "magnate_wins", "magnate_rewarded_attempts_today", "magnate_attempts_reset_at",
    "magnate_hourly_attempts", "magnate_hour_started_at",
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'magnate_reward'")

    op.create_table(
        "magnate_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="lobby"),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invite_code", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_state", sa.JSON(), nullable=True),
        sa.Column("next_deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finish_reason", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("invite_code", name="uq_magnate_matches_invite_code"),
    )
    op.create_index("ix_magnate_matches_mode", "magnate_matches", ["mode"])
    op.create_index("ix_magnate_matches_status", "magnate_matches", ["status"])
    op.create_index("ix_magnate_matches_next_deadline_at", "magnate_matches", ["next_deadline_at"])
    op.create_index("ix_magnate_matches_created_at", "magnate_matches", ["created_at"])

    op.create_table(
        "magnate_seats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "match_id", sa.Integer(), sa.ForeignKey("magnate_matches.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("replaced_by_bot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("place", sa.Integer(), nullable=True),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("match_id", "seat", name="uq_magnate_seats_match_seat"),
        sa.UniqueConstraint("match_id", "user_id", name="uq_magnate_seats_match_user"),
    )
    op.create_index("ix_magnate_seats_match_id", "magnate_seats", ["match_id"])
    op.create_index("ix_magnate_seats_user_id", "magnate_seats", ["user_id"])

    op.add_column("users", sa.Column("magnate_wins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("magnate_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("magnate_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("magnate_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("magnate_hour_started_at", sa.DateTime(timezone=True), nullable=True))

    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, default in CONFIG_JSON_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'::json")))
    op.add_column("game_config", sa.Column("magnate_board", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("magnate_cards", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_config", "magnate_cards")
    op.drop_column("game_config", "magnate_board")
    for name, _ in reversed(CONFIG_JSON_COLUMNS):
        op.drop_column("game_config", name)
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    for name in reversed(USER_COLUMNS):
        op.drop_column("users", name)
    op.drop_index("ix_magnate_seats_user_id", table_name="magnate_seats")
    op.drop_index("ix_magnate_seats_match_id", table_name="magnate_seats")
    op.drop_table("magnate_seats")
    for index in (
        "ix_magnate_matches_created_at", "ix_magnate_matches_next_deadline_at",
        "ix_magnate_matches_status", "ix_magnate_matches_mode",
    ):
        op.drop_index(index, table_name="magnate_matches")
    op.drop_table("magnate_matches")
    # Postgres cannot drop an enum value — 'magnate_reward' stays (same as
    # earlier migrations).
