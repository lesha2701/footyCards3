"""ClubDailyClaim: one club-budget daily reward per member per day

Revision ID: 0060
Revises: 0059
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "club_daily_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_date", sa.Date(), nullable=False),
    )
    op.create_index("ix_club_daily_claims_club_id", "club_daily_claims", ["club_id"])
    op.create_index("ix_club_daily_claims_user_id", "club_daily_claims", ["user_id"])
    op.create_unique_constraint(
        "uq_club_daily_claim_once_per_day", "club_daily_claims", ["club_id", "user_id", "claim_date"]
    )


def downgrade() -> None:
    op.drop_table("club_daily_claims")
