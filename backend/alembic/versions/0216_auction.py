"""«Трансферный рынок»: auction lots + bids, «Агентская лицензия» (only
agents list lots), GameConfig settings, auction transaction and
notification types.

Revision ID: 0216
Revises: 0215
Create Date: 2026-10-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0216"
down_revision: Union[str, None] = "0215"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRANSACTION_TYPES = ("auction_bid", "auction_refund", "auction_buy_now", "auction_sale")
NOTIFICATION_TYPES = ("auction_outbid", "auction_won", "auction_sold", "auction_expired", "auction_removed")
CONFIG_INT_COLUMNS = (
    ("auction_fee_pct", "10"),
    ("auction_fixed_duration_hours", "72"),
    ("auction_min_increment_pct", "5"),
    ("auction_min_increment_coins", "10"),
    ("auction_min_price", "10"),
    ("auction_max_active_lots", "5"),
    ("auction_snipe_window_seconds", "120"),
    ("auction_snipe_extend_seconds", "120"),
    ("auction_min_account_age_days", "0"),
    ("auction_max_wins_per_seller_daily", "3"),
    ("agent_license_stars", "99"),
    ("agent_license_days", "30"),
    ("agent_license_min_account_age_days", "30"),
)
CONFIG_BOOL_COLUMNS = (
    ("auction_enabled", sa.false()),
    ("agent_license_enabled", sa.true()),
    ("agent_license_requires_verified", sa.true()),
)


def upgrade() -> None:
    for value in TRANSACTION_TYPES:
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    for value in NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "auction_lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("kind", sa.String(16), nullable=False, server_default="auction"),
        sa.Column("start_price", sa.Integer(), nullable=False),
        sa.Column("buy_now_price", sa.Integer(), nullable=True),
        sa.Column("current_bid", sa.Integer(), nullable=True),
        sa.Column("current_bidder_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bid_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fee_pct", sa.Integer(), nullable=False),
        sa.Column("duration_hours", sa.Integer(), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("winner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("final_price", sa.Integer(), nullable=True),
        sa.Column("fee_amount", sa.Integer(), nullable=True),
        sa.Column("close_reason", sa.String(255), nullable=True),
        sa.CheckConstraint("start_price > 0", name="ck_auction_lots_start_price"),
        sa.CheckConstraint(
            "buy_now_price IS NULL OR buy_now_price > start_price OR (kind = 'fixed' AND buy_now_price = start_price)",
            name="ck_auction_lots_buy_now_price",
        ),
        sa.CheckConstraint("kind IN ('auction', 'fixed')", name="ck_auction_lots_kind"),
    )
    for column in ("seller_id", "user_card_id", "player_id", "status", "kind", "current_bidder_id", "ends_at", "created_at", "winner_id"):
        op.create_index(f"ix_auction_lots_{column}", "auction_lots", [column])
    op.create_index(
        "uq_auction_lots_active_card", "auction_lots", ["user_card_id"], unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "auction_bids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lot_id", sa.Integer(), sa.ForeignKey("auction_lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bidder_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="bid"),
        sa.Column("status", sa.String(16), nullable=False, server_default="leading"),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("lot_id", "amount", name="uq_auction_bids_lot_amount"),
        sa.UniqueConstraint("bidder_id", "idempotency_key", name="uq_auction_bids_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_auction_bids_amount"),
    )
    op.create_index("ix_auction_bids_lot_id", "auction_bids", ["lot_id"])
    op.create_index("ix_auction_bids_bidder_id", "auction_bids", ["bidder_id"])

    for name, default in CONFIG_BOOL_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Boolean(), nullable=False, server_default=default))
    op.add_column(
        "game_config",
        sa.Column("auction_durations_hours", sa.JSON(), nullable=False, server_default=sa.text("'[1, 6, 24]'::json")),
    )
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))

    op.create_table(
        "agent_licenses",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_bought_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_bought_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("purchases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(255), nullable=True),
    )
    op.create_index("ix_agent_licenses_expires_at", "agent_licenses", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_licenses_expires_at", table_name="agent_licenses")
    op.drop_table("agent_licenses")
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("game_config", "auction_durations_hours")
    for name, _ in reversed(CONFIG_BOOL_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_index("ix_auction_bids_bidder_id", table_name="auction_bids")
    op.drop_index("ix_auction_bids_lot_id", table_name="auction_bids")
    op.drop_table("auction_bids")
    op.drop_index("uq_auction_lots_active_card", table_name="auction_lots")
    for column in ("seller_id", "user_card_id", "player_id", "status", "kind", "current_bidder_id", "ends_at", "created_at", "winner_id"):
        op.drop_index(f"ix_auction_lots_{column}", table_name="auction_lots")
    op.drop_table("auction_lots")
    # Postgres cannot drop an enum value — the auction_* values stay (same as
    # earlier migrations).
