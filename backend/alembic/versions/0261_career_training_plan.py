"""«Карьера тренера»: the training plan, a second session and an intensity.

Revision ID: 0261
Revises: 0260
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0261"
down_revision: Union[str, None] = "0260"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("career_participants", sa.Column("training_extra", sa.String(16), nullable=True))
    op.add_column("career_participants", sa.Column("training_intensity", sa.String(8), nullable=False, server_default="normal"))
    op.add_column("career_participants", sa.Column("training_program", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("career_participants", "training_program")
    op.drop_column("career_participants", "training_intensity")
    op.drop_column("career_participants", "training_extra")
