"""Raise the Тактико position-match bonus from 15% to 20%

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("game_config", "tactico_phase_bonus_pct", server_default="0.20")
    op.execute(
        "UPDATE game_config SET tactico_phase_bonus_pct = 0.20 WHERE tactico_phase_bonus_pct = 0.15"
    )


def downgrade() -> None:
    op.alter_column("game_config", "tactico_phase_bonus_pct", server_default="0.15")
    op.execute(
        "UPDATE game_config SET tactico_phase_bonus_pct = 0.15 WHERE tactico_phase_bonus_pct = 0.20"
    )
