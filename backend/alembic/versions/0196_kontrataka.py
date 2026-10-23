"""«Контратака»: kontra_battles (arena attacks and weekly boss attempts),
kontra_gear («Тактические комплекты»), users' squad / rating / hourly and
daily counters / boss attempts / arena offers, GameConfig settings (off by
default) and the transaction types.

Revision ID: 0196
Revises: 0195
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0196"
down_revision: Union[str, None] = "0195"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("kontra_arena_reward_win", "80"),
    ("kontra_arena_reward_loss", "20"),
    ("kontra_daily_limit", "10"),
    ("kontra_rating_win", "20"),
    ("kontra_rating_loss", "10"),
    ("kontra_arena_max_rounds", "60"),
    ("kontra_boss_daily_attempts", "3"),
    ("kontra_boss_max_rounds", "25"),
    ("kontra_gear_drop_boss_pct", "35"),
    ("kontra_gear_drop_arena_pct", "15"),
    ("kontra_chest_coins", "1500"),
    ("kontra_chest_stars", "25"),
)
USER_COLUMNS = (
    ("kontra_rating", sa.Integer(), "1000"),
    ("kontra_hourly_attempts", sa.Integer(), "0"),
    ("kontra_rewarded_attempts_today", sa.Integer(), "0"),
    ("kontra_boss_attempts_today", sa.Integer(), "0"),
)
USER_NULLABLE = (
    ("kontra_squad", sa.JSON()),
    ("kontra_hour_started_at", sa.DateTime(timezone=True)),
    ("kontra_attempts_reset_at", sa.DateTime(timezone=True)),
    ("kontra_boss_reset_at", sa.DateTime(timezone=True)),
    ("kontra_arena_offers", sa.JSON()),
)


def upgrade() -> None:
    for value in ("kontra_reward", "kontra_chest_purchase"):
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "kontra_battles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("damage", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("boss_week", sa.Date(), nullable=True),
        sa.Column("gear_drop_id", sa.Integer(), nullable=True),
        sa.Column("server_state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    for col in ("user_id", "opponent_user_id", "status", "boss_week", "created_at"):
        op.create_index(f"ix_kontra_battles_{col}", "kontra_battles", [col])

    op.create_table(
        "kontra_gear",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.String(16), nullable=False),
        sa.Column("set_code", sa.String(16), nullable=False),
        sa.Column("rarity", sa.String(16), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_kontra_gear_user_id", "kontra_gear", ["user_id"])

    for name, type_, default in USER_COLUMNS:
        op.add_column("users", sa.Column(name, type_, nullable=False, server_default=default))
    for name, type_ in USER_NULLABLE:
        op.add_column("users", sa.Column(name, type_, nullable=True))

    op.add_column("game_config", sa.Column("kontra_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("kontra_boss_week_hp", sa.BigInteger(), nullable=False, server_default="50000000"))
    op.add_column("game_config", sa.Column(
        "kontra_boss_reward_tiers", sa.JSON(), nullable=False,
        server_default='[[0, 20], [20000, 50], [60000, 100], [150000, 200], [400000, 400]]',
    ))


def downgrade() -> None:
    op.drop_column("game_config", "kontra_boss_reward_tiers")
    op.drop_column("game_config", "kontra_boss_week_hp")
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "kontra_enabled")
    for name, _ in reversed(USER_NULLABLE):
        op.drop_column("users", name)
    for name, _, _ in reversed(USER_COLUMNS):
        op.drop_column("users", name)
    op.drop_index("ix_kontra_gear_user_id", table_name="kontra_gear")
    op.drop_table("kontra_gear")
    for col in ("user_id", "opponent_user_id", "status", "boss_week", "created_at"):
        op.drop_index(f"ix_kontra_battles_{col}", table_name="kontra_battles")
    op.drop_table("kontra_battles")
    # Postgres cannot drop enum values — the transaction types stay.
