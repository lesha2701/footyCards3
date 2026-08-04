"""Allow uploading an image for a Badge instead of only a text/emoji icon.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("badges", sa.Column("image_path", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("badges", "image_path")
