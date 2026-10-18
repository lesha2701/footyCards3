"""Club emblem constructor (paid layers on the club logo) and «Казна за
Stars» (members top up the club budget; «Доска меценатов», sponsor badges).
The emblem catalog rows are inserted by club_emblem_service.ensure_catalog
on first use.

Revision ID: 0169
Revises: 0168
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0169"
down_revision: Union[str, None] = "0168"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLUB_COLUMNS = (
    ("logo_color2", sa.String(16)),
    ("logo_pattern", sa.String(32)),
    ("logo_symbol", sa.String(32)),
    ("logo_letters", sa.String(3)),
    ("logo_outline", sa.String(32)),
    ("logo_effect", sa.String(32)),
)
CONFIG_INT_COLUMNS = (
    ("club_donation_coins_per_star", "15"),
    ("club_sponsor_silver_stars", "250"),
    ("club_sponsor_gold_stars", "1000"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_donation'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'stars_donation'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'emblem_purchase'")

    for column, type_ in CLUB_COLUMNS:
        op.add_column("clubs", sa.Column(column, type_, nullable=True))
    op.add_column("clubs", sa.Column("logo_outline_thin", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.create_table(
        "club_emblem_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("style_key", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("kind", "style_key", name="uq_club_emblem_items_kind_style"),
    )
    op.create_table(
        "club_emblem_unlocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("club_emblem_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("club_id", "item_id", name="uq_club_emblem_unlocks_club_item"),
    )
    op.create_index("ix_club_emblem_unlocks_club_id", "club_emblem_unlocks", ["club_id"])
    op.create_table(
        "club_donations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("stars_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("invoice_id", name="uq_club_donations_invoice_id"),
    )
    op.create_index("ix_club_donations_club_id", "club_donations", ["club_id"])
    op.create_index("ix_club_donations_user_id", "club_donations", ["user_id"])

    op.add_column("game_config", sa.Column("club_emblems_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("club_donation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column(
        "club_donation_star_options", sa.JSON(), nullable=False, server_default=sa.text("'[25, 50, 100, 250, 500]'::json"),
    ))


def downgrade() -> None:
    op.drop_column("game_config", "club_donation_star_options")
    for column, _default in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", column)
    op.drop_column("game_config", "club_donation_enabled")
    op.drop_column("game_config", "club_emblems_enabled")
    op.drop_index("ix_club_donations_user_id", table_name="club_donations")
    op.drop_index("ix_club_donations_club_id", table_name="club_donations")
    op.drop_table("club_donations")
    op.drop_index("ix_club_emblem_unlocks_club_id", table_name="club_emblem_unlocks")
    op.drop_table("club_emblem_unlocks")
    op.drop_table("club_emblem_items")
    op.drop_column("clubs", "logo_outline_thin")
    for column, _type in reversed(CLUB_COLUMNS):
        op.drop_column("clubs", column)
    # Enum values stay: Postgres can't drop enum values.
