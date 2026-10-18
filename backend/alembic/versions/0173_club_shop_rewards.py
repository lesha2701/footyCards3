"""«Клубный магазин» and club-wide rewards every member claims for
themselves (shop purchases now, weekly quests and club wars later).

Revision ID: 0173
Revises: 0172
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0173"
down_revision: Union[str, None] = "0172"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _bundle_columns(prefix: str = "") -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(f"{prefix}pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column(f"{prefix}card_rarity", sa.String(16), nullable=True),
        sa.Column(f"{prefix}badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True),
        sa.Column(f"{prefix}cosmetic_id", sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True),
    ]


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'club_reward'")
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'club_reward'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'shop_purchase'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_reward_available'")

    op.create_table(
        "club_reward_grants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("source_ref_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(128), nullable=False),
        *_bundle_columns(),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_club_reward_grants_club_id_expires", "club_reward_grants", ["club_id", "expires_at"])
    op.create_table(
        "club_reward_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grant_id", sa.Integer(), sa.ForeignKey("club_reward_grants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("grant_id", "user_id", name="uq_club_reward_claims_grant_user"),
    )
    op.create_index("ix_club_reward_claims_user_id", "club_reward_claims", ["user_id"])
    items = op.create_table(
        "club_shop_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), nullable=False, server_default=""),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("weekly_limit", sa.Integer(), nullable=False, server_default="1"),
        *_bundle_columns("reward_"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "club_shop_purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("club_shop_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_shop_purchases_club_week", "club_shop_purchases", ["club_id", "week_start"])
    # A starter assortment; prices and rewards are edited in the admin panel.
    op.bulk_insert(items, [
        {"name": "Премия команде", "description": "Каждый участник получает монеты", "price": 5000,
         "weekly_limit": 1, "reward_coins": 300, "sort_order": 0},
        {"name": "Скаутский отчёт", "description": "Каждый участник получает редкую карточку", "price": 8000,
         "weekly_limit": 1, "reward_coins": 0, "reward_card_rarity": "rare", "sort_order": 1},
        {"name": "Сборы чемпионов", "description": "Каждый участник получает эпическую карточку", "price": 20000,
         "weekly_limit": 1, "reward_coins": 0, "reward_card_rarity": "epic", "sort_order": 2},
    ])


def downgrade() -> None:
    op.drop_index("ix_club_shop_purchases_club_week", table_name="club_shop_purchases")
    op.drop_table("club_shop_purchases")
    op.drop_table("club_shop_items")
    op.drop_index("ix_club_reward_claims_user_id", table_name="club_reward_claims")
    op.drop_table("club_reward_claims")
    op.drop_index("ix_club_reward_grants_club_id_expires", table_name="club_reward_grants")
    op.drop_table("club_reward_grants")
    # Enum values stay: Postgres can't drop enum values.
