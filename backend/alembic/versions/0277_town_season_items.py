"""«Сезонный город»: limited seasonal decorations bought for Stars, numbered per item.

Revision ID: 0277
Revises: 0276
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0277"
down_revision: Union[str, None] = "0276"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_town_season_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("serial", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "code", name="uq_town_season_item_user"),
        sa.UniqueConstraint("code", "serial", name="uq_town_season_item_serial"),
    )
    op.create_index("ix_user_town_season_items_user_id", "user_town_season_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_town_season_items_user_id", table_name="user_town_season_items")
    op.drop_table("user_town_season_items")
