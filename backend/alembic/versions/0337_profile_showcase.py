"""«Витрина» of the profile: users.showcase_card_ids

Revision ID: 0337
Revises: 0336
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0337"
down_revision: Union[str, None] = "0336"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("showcase_card_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "showcase_card_ids")
