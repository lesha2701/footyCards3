"""«Респект» on profiles: profile_respects

Revision ID: 0340
Revises: 0339
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0340"
down_revision: Union[str, None] = "0339"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_respects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("giver_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("giver_id", "target_id", "day", name="uq_profile_respect_day"),
    )
    op.create_index("ix_profile_respects_giver_id", "profile_respects", ["giver_id"])
    op.create_index("ix_profile_respects_target_id", "profile_respects", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_respects_target_id", table_name="profile_respects")
    op.drop_index("ix_profile_respects_giver_id", table_name="profile_respects")
    op.drop_table("profile_respects")
