"""Support repeatable tasks: snapshot the metric baseline at (re)assignment
time so progress is tracked relative to it, not the player's lifetime total.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_tasks", sa.Column("metric_baseline", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("user_tasks", "metric_baseline")
