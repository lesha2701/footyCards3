"""«Мордобой» on: the game is switched on for everyone and new configs
start with it on (an admin can still switch it off in «Игры»).

Revision ID: 0191
Revises: 0190
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0191"
down_revision: Union[str, None] = "0190"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "mordoboi_enabled", server_default=sa.true())
    op.execute("UPDATE game_config SET mordoboi_enabled = true")


def downgrade() -> None:
    op.alter_column("game_config", "mordoboi_enabled", server_default=sa.false())
