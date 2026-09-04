"""Allow a diamond upgrade tier's per-rarity cost to be unset (unavailable)

Revision ID: 0088
Revises: 0087
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0088"
down_revision: Union[str, None] = "0087"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in ("common_cost", "rare_cost", "epic_cost", "legendary_cost"):
        op.alter_column("diamond_upgrade_tiers", column, existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    for column in ("common_cost", "rare_cost", "epic_cost", "legendary_cost"):
        op.alter_column("diamond_upgrade_tiers", column, existing_type=sa.Integer(), nullable=False)
