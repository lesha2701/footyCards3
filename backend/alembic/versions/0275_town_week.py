"""«Город недели»: the weekly ranking of towns by likes, guests and houses,
its settled weeks (town_weeks) and rewarded places (town_week_results).

Revision ID: 0275
Revises: 0274
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0275"
down_revision: Union[str, None] = "0274"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'town_week'")
    op.create_table(
        "town_weeks",
        sa.Column("week", sa.String(10), primary_key=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "town_week_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week", sa.String(10), nullable=False, index=True),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("week", "place", name="uq_town_week_place"),
        sa.UniqueConstraint("week", "user_id", name="uq_town_week_user"),
    )


def downgrade() -> None:
    op.drop_table("town_week_results")
    op.drop_table("town_weeks")
