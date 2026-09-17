"""Card Arena lineups become 5 named templates per user (template_index
1..5, one active) instead of a single row — templates 2-5 are lazily
created by lineup_service on first read, not backfilled here.

Revision ID: 0116
Revises: 0115
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0116"
down_revision: Union[str, None] = "0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lineups", sa.Column("template_index", sa.Integer(), nullable=False, server_default="1"))
    op.create_unique_constraint("uq_lineup_user_template", "lineups", ["user_id", "template_index"])


def downgrade() -> None:
    op.drop_constraint("uq_lineup_user_template", "lineups", type_="unique")
    op.drop_column("lineups", "template_index")
