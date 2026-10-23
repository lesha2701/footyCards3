"""«Контратака» is switched on at launch.

Revision ID: 0197
Revises: 0196
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0197"
down_revision: Union[str, None] = "0196"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "kontra_enabled", server_default=sa.true())
    op.execute("UPDATE game_config SET kontra_enabled = true")


def downgrade() -> None:
    op.alter_column("game_config", "kontra_enabled", server_default=sa.false())
    op.execute("UPDATE game_config SET kontra_enabled = false")
