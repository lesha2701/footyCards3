"""«Преторианец» badge art (static/badges/praetorian.webp) — only when an
admin hasn't uploaded one already.

Revision ID: 0301
Revises: 0300
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0301"
down_revision: Union[str, None] = "0300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGE = "badges/praetorian.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE badges SET image_path = :img "
        "WHERE id = (SELECT stars_praetorian_badge_id FROM game_config WHERE id = 1) "
        "AND image_path IS NULL"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE badges SET image_path = NULL WHERE image_path = :img"), {"img": IMAGE})
