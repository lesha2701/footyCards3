"""Admin-configurable candidate reward pool for the daily-reward cycle:
daily_reward_options holds several possible reward configs per day-slot
(1-7) so daily_reward_service can pick one at random per user each time
they start a fresh 7-day cycle, instead of a single fixed amount per day.
Schema only — daily_reward_service seeds sensible defaults lazily on first
read (same pattern as GameConfig's singleton row), so no data migration is
needed here.

Revision ID: 0115
Revises: 0112
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0115"
down_revision: Union[str, None] = "0112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_reward_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column("option_index", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("free_pack_slug", sa.String(), nullable=True),
        sa.Column("grants_random_card", sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("day", "option_index", name="uq_daily_reward_option_day_index"),
    )


def downgrade() -> None:
    op.drop_table("daily_reward_options")
