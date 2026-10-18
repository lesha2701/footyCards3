"""Club roles: «вице-капитан» (successor, emblem) and «казначей» (budget),
the captain's «only the treasurer spends the budget» switch, and the
«новый участник в клубе» notification.

Revision ID: 0171
Revises: 0170
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0171"
down_revision: Union[str, None] = "0170"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_role_enum ADD VALUE IF NOT EXISTS 'vice_captain'")
    op.execute("ALTER TYPE club_role_enum ADD VALUE IF NOT EXISTS 'treasurer'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_member_joined'")
    op.add_column("clubs", sa.Column("budget_treasurer_only", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("clubs", "budget_treasurer_only")
    # Enum values stay: Postgres can't drop enum values.
