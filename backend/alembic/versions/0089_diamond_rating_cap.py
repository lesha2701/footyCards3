"""Add a configurable soft rating cap for diamond card leveling

Revision ID: 0089
Revises: 0088
Create Date: 2026-09-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0089"
down_revision: Union[str, None] = "0088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("diamond_rating_cap", sa.Integer(), nullable=False, server_default="95"))
    op.add_column(
        "game_config", sa.Column("diamond_rating_cap_enabled", sa.Boolean(), nullable=False, server_default=sa.true())
    )


def downgrade() -> None:
    op.drop_column("game_config", "diamond_rating_cap_enabled")
    op.drop_column("game_config", "diamond_rating_cap")
