"""Leagues: tier ladder + reward claims

Revision ID: 0047
Revises: 0046
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'league_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'league_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'league_promoted'")

    op.create_table(
        "league_tiers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("min_rating", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default="🏅"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_league_tiers_min_rating", "league_tiers", ["min_rating"])

    op.create_table(
        "user_league_reward_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "league_tier_id", sa.Integer(), sa.ForeignKey("league_tiers.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("reward_coins", sa.Integer(), nullable=False),
        sa.Column("reward_pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_user_league_reward_claims_user_id", "user_league_reward_claims", ["user_id"])
    op.create_index("ix_user_league_reward_claims_league_tier_id", "user_league_reward_claims", ["league_tier_id"])
    op.create_unique_constraint(
        "uq_user_league_reward_claims_user_tier", "user_league_reward_claims", ["user_id", "league_tier_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_league_reward_claims_league_tier_id", table_name="user_league_reward_claims")
    op.drop_index("ix_user_league_reward_claims_user_id", table_name="user_league_reward_claims")
    op.drop_table("user_league_reward_claims")
    op.drop_table("league_tiers")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving the three new enum
    # values in place on downgrade is harmless (mirrors every prior
    # migration's same note).
