"""«Свой в клубе» badge art (static/badges/svoy_v_klube.webp) — only when
an admin hasn't uploaded one already.

Revision ID: 0234
Revises: 0233
Create Date: 2026-11-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0234"
down_revision: Union[str, None] = "0233"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGE = "badges/svoy_v_klube.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE badges SET image_path = :img WHERE name = 'Свой в клубе' AND image_path IS NULL"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE badges SET image_path = NULL WHERE image_path = :img"), {"img": IMAGE})
