"""FUT Draft: progressive per-round bot strength boost (ramps up to a
configurable % by the final match), so a strong squad doesn't steamroll
every round at the same relative difficulty.

Revision ID: 0113
Revises: 0112
Create Date: 2026-09-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0113"
down_revision: Union[str, None] = "0112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("fut_draft_round_bot_boost_pct", sa.Numeric(4, 2), nullable=False, server_default="20.0"))


def downgrade() -> None:
    op.drop_column("game_config", "fut_draft_round_bot_boost_pct")
