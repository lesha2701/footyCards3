"""Time players spend in each section of the Mini App, per local day

Revision ID: 0335
Revises: 0334
Create Date: 2026-11-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0335"
down_revision: Union[str, None] = "0334"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "section_time_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("day", "section", "user_id"),
    )
    op.create_index("ix_section_time_daily_user", "section_time_daily", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_section_time_daily_user", table_name="section_time_daily")
    op.drop_table("section_time_daily")
