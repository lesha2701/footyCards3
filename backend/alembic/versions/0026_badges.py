"""Badge system: admin-defined flairs granted as a configurable Stars-pack
reward, displayed next to a user's name (profile, rankings, trades).

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'stars_pack_bonus_coins'")

    op.create_table(
        "badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("icon", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_badges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),
    )
    op.create_index("ix_user_badges_user_id", "user_badges", ["user_id"])
    op.create_index("ix_user_badges_badge_id", "user_badges", ["badge_id"])

    op.add_column(
        "users",
        sa.Column("active_badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True),
    )

    op.add_column("packs", sa.Column("bonus_coins", sa.Integer(), nullable=True))
    op.add_column("packs", sa.Column("badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True))


def downgrade() -> None:
    op.drop_column("packs", "badge_id")
    op.drop_column("packs", "bonus_coins")

    op.drop_column("users", "active_badge_id")

    op.drop_index("ix_user_badges_badge_id", table_name="user_badges")
    op.drop_index("ix_user_badges_user_id", table_name="user_badges")
    op.drop_table("user_badges")

    op.drop_table("badges")
