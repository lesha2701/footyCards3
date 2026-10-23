"""Wing-back positions LWB / RWB (DEF line; on position in LB / RB slots
and vice versa — lineup_service.on_ideal_position) and the 3-4-3 formation
(code only).

Revision ID: 0144
Revises: 0143
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0144"
down_revision: Union[str, None] = "0143"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE position_enum ADD VALUE IF NOT EXISTS 'LWB'")
    op.execute("ALTER TYPE position_enum ADD VALUE IF NOT EXISTS 'RWB'")


def downgrade() -> None:
    # PostgreSQL can't drop enum values; they stay unused without the code.
    pass
