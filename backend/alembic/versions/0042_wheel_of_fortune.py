"""Wheel of fortune: weighted prize pool, spin history, Stars-spin support

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

wheel_prize_type_enum = postgresql.ENUM("coins", "pack", "card_rarity", "badge", name="wheel_prize_type_enum", create_type=False)
wheel_spin_source_enum = postgresql.ENUM("free", "coins", "stars", name="wheel_spin_source_enum", create_type=False)

NEW_ENUMS = [wheel_prize_type_enum, wheel_spin_source_enum]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'wheel'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'wheel_spin_cost'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'wheel_spin_reward'")

    op.add_column("users", sa.Column("wheel_free_spins_used_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("wheel_spins_reset_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("game_config", sa.Column("wheel_free_spins_per_day", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("wheel_spin_cost_coins", sa.Integer(), nullable=False, server_default="1000"))
    op.add_column("game_config", sa.Column("wheel_spin_cost_stars", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("wheel_duplicate_badge_coins", sa.Integer(), nullable=False, server_default="200"))

    op.create_table(
        "wheel_prizes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prize_type", wheel_prize_type_enum, nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coins_amount", sa.Integer(), nullable=True),
        sa.Column("pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("card_rarity", postgresql.ENUM(name="rarity_enum", create_type=False), nullable=True),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "wheel_spins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("prize_id", sa.Integer(), sa.ForeignKey("wheel_prizes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source", wheel_spin_source_enum, nullable=False),
        sa.Column("pack_opening_id", sa.Integer(), sa.ForeignKey("pack_openings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("badge_granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("duplicate_badge_coins", sa.Integer(), nullable=True),
        sa.Column("coins_amount", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_wheel_spins_user_id", "wheel_spins", ["user_id"])

    op.add_column("stars_invoices", sa.Column("is_wheel_spin", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("stars_invoices", sa.Column("wheel_spin_id", sa.Integer(), sa.ForeignKey("wheel_spins.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("stars_invoices", "wheel_spin_id")
    op.drop_column("stars_invoices", "is_wheel_spin")

    op.drop_index("ix_wheel_spins_user_id", table_name="wheel_spins")
    op.drop_table("wheel_spins")
    op.drop_table("wheel_prizes")

    op.drop_column("game_config", "wheel_duplicate_badge_coins")
    op.drop_column("game_config", "wheel_spin_cost_stars")
    op.drop_column("game_config", "wheel_spin_cost_coins")
    op.drop_column("game_config", "wheel_free_spins_per_day")

    op.drop_column("users", "wheel_spins_reset_at")
    op.drop_column("users", "wheel_free_spins_used_today")

    for enum_type in NEW_ENUMS:
        enum_type.drop(op.get_bind(), checkfirst=True)
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'wheel'/
    # 'wheel_spin_cost'/'wheel_spin_reward' on their enums on downgrade is
    # harmless (mirrors 0035's note on the same limitation).
