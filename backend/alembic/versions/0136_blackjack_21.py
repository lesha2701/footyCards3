"""«21: Добавленное время»: wheel prize pools (regular/golden/jackpot), the
blackjack_matches table, per-user entry counters, GameConfig settings, the
Stars entry invoice flag, and conservative starter prizes for the golden
and jackpot pools.

Revision ID: 0136
Revises: 0135
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0136"
down_revision: Union[str, None] = "0135"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

wheel_prize_pool_enum = postgresql.ENUM("regular", "golden", "jackpot", name="wheel_prize_pool_enum", create_type=False)

CONFIG_INT_COLUMNS = (
    ("blackjack_free_per_day", "1"),
    ("blackjack_stars_cost", "10"),
    ("blackjack_paid_daily_limit", "10"),
    ("blackjack_consolation_coins", "25"),
)

USER_INT_COLUMNS = (
    "blackjack_free_used_today", "blackjack_paid_bought_today", "blackjack_paid_entries", "blackjack_replay_entries",
)

# Starter prizes (prize_type, coins_amount, card_rarity, weight). Coins and
# rarity cards only — no FK to packs/badges that may not exist everywhere.
# Expected value at dev quick-sell averages (epic≈120, legendary≈400):
# golden ≈ 1600 coins/spin, jackpot ≈ 5600 coins/spin. See the report in
# the PR / commit message for the reasoning; admins tune these on the
# «Колесо фортуны» admin page, which shows each pool's live EV.
STARTER_PRIZES = {
    "golden": (
        ("coins", 1000, None, 35),
        ("coins", 2000, None, 25),
        ("coins", 3000, None, 15),
        ("coins", 5000, None, 5),
        ("card_rarity", None, "epic", 12),
        ("card_rarity", None, "legendary", 8),
    ),
    "jackpot": (
        ("coins", 5000, None, 40),
        ("coins", 8000, None, 25),
        ("coins", 15000, None, 10),
        ("card_rarity", None, "legendary", 25),
    ),
}


def upgrade() -> None:
    op.execute("ALTER TYPE wheel_spin_source_enum ADD VALUE IF NOT EXISTS 'blackjack'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'blackjack_consolation'")

    bind = op.get_bind()
    wheel_prize_pool_enum.create(bind, checkfirst=True)
    op.add_column("wheel_prizes", sa.Column("pool", wheel_prize_pool_enum, nullable=False, server_default="regular"))
    op.create_index("ix_wheel_prizes_pool", "wheel_prizes", ["pool"])

    for name in USER_INT_COLUMNS:
        op.add_column("users", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("blackjack_day_reset_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("blackjack_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))

    op.add_column(
        "stars_invoices", sa.Column("is_blackjack_entry", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "blackjack_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="in_progress"),
        sa.Column("entry_source", sa.String(16), nullable=False),
        sa.Column("server_state", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("outcome_reason", sa.String(32), nullable=True),
        sa.Column("reward_pool", sa.String(16), nullable=True),
        sa.Column("consolation_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_blackjack_matches_user_id", "blackjack_matches", ["user_id"])
    op.create_index("ix_blackjack_matches_created_at", "blackjack_matches", ["created_at"])
    op.create_index(
        "uq_blackjack_matches_one_active", "blackjack_matches", ["user_id"], unique=True,
        postgresql_where=sa.text("status = 'in_progress'"),
    )

    op.add_column(
        "wheel_spins",
        sa.Column(
            "blackjack_match_id", sa.Integer(), sa.ForeignKey("blackjack_matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint("uq_wheel_spins_blackjack_match_id", "wheel_spins", ["blackjack_match_id"])

    # Idempotent seed: only fills a pool that has no prizes at all, so a
    # re-run (or an admin who already configured the pool) is left alone.
    for pool, prizes in STARTER_PRIZES.items():
        existing = bind.execute(
            sa.text("SELECT COUNT(*) FROM wheel_prizes WHERE pool = CAST(:pool AS wheel_prize_pool_enum)"),
            {"pool": pool},
        ).scalar()
        if existing:
            continue
        for sort_order, (prize_type, coins, rarity, weight) in enumerate(prizes):
            bind.execute(
                sa.text(
                    "INSERT INTO wheel_prizes (prize_type, pool, weight, is_active, sort_order, coins_amount, card_rarity, created_at, updated_at) "
                    "VALUES (CAST(:prize_type AS wheel_prize_type_enum), CAST(:pool AS wheel_prize_pool_enum), :weight, true, "
                    ":sort_order, :coins, CAST(:rarity AS rarity_enum), now(), now())"
                ),
                {"prize_type": prize_type, "pool": pool, "weight": weight, "sort_order": sort_order, "coins": coins, "rarity": rarity},
            )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_constraint("uq_wheel_spins_blackjack_match_id", "wheel_spins", type_="unique")
    op.drop_column("wheel_spins", "blackjack_match_id")
    # Spins of non-regular prizes reference rows we're about to delete.
    bind.execute(sa.text(
        "DELETE FROM wheel_spins WHERE prize_id IN (SELECT id FROM wheel_prizes WHERE pool <> 'regular')"
    ))
    bind.execute(sa.text("DELETE FROM wheel_prizes WHERE pool <> 'regular'"))
    op.drop_index("uq_blackjack_matches_one_active", table_name="blackjack_matches")
    op.drop_index("ix_blackjack_matches_created_at", table_name="blackjack_matches")
    op.drop_index("ix_blackjack_matches_user_id", table_name="blackjack_matches")
    op.drop_table("blackjack_matches")
    op.drop_column("stars_invoices", "is_blackjack_entry")
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "blackjack_enabled")
    op.drop_column("users", "blackjack_day_reset_at")
    for name in reversed(USER_INT_COLUMNS):
        op.drop_column("users", name)
    op.drop_index("ix_wheel_prizes_pool", table_name="wheel_prizes")
    op.drop_column("wheel_prizes", "pool")
    wheel_prize_pool_enum.drop(bind, checkfirst=True)
    # Postgres cannot drop individual enum values — 'blackjack' /
    # 'blackjack_consolation' stay (same as earlier migrations).
