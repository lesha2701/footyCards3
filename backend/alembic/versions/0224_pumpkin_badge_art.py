"""«Тыква 2026» badge art (static/badges/halloween_pumpkin_2026.webp) —
only when an admin hasn't uploaded one already.

Revision ID: 0224
Revises: 0223
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0224"
down_revision: Union[str, None] = "0223"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGE = "badges/halloween_pumpkin_2026.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE badges SET image_path = :img WHERE name = 'Тыква 2026' AND image_path IS NULL"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE badges SET image_path = NULL WHERE image_path = :img"), {"img": IMAGE})
