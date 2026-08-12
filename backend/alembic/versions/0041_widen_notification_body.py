"""Widen notifications.body to match AdminBroadcastCreate's max_length

The broadcast schema allows up to 1024 characters, but the body column
was only VARCHAR(512) — any admin broadcast longer than 512 chars passed
request validation and then crashed the insert with
StringDataRightTruncationError.

Revision ID: 0041
Revises: 0040
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("notifications", "body", type_=sa.String(1024), existing_type=sa.String(512))


def downgrade() -> None:
    op.alter_column("notifications", "body", type_=sa.String(512), existing_type=sa.String(1024))
