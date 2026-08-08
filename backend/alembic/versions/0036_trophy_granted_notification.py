"""Add trophy_granted to notification_type_enum so recipients are told a trophy arrived

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'trophy_granted'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'trophy_granted' on
    # the enum on downgrade is harmless (mirrors 0029's note).
    pass
