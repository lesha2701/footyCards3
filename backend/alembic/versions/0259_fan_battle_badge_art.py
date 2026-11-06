"""«Фанат 2026» and «Чемпион трибун 2026» badge art (static/badges/) — only
when an admin hasn't uploaded one already.

Revision ID: 0259
Revises: 0258
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0259"
down_revision: Union[str, None] = "0258"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGES = {
    "Фанат 2026": "badges/fan_2026.webp",
    "Чемпион трибун 2026": "badges/tribune_champion_2026.webp",
}


def upgrade() -> None:
    for name, image in IMAGES.items():
        op.get_bind().execute(sa.text(
            "UPDATE badges SET image_path = :img WHERE name = :name AND image_path IS NULL"
        ), {"img": image, "name": name})


def downgrade() -> None:
    for image in IMAGES.values():
        op.get_bind().execute(sa.text("UPDATE badges SET image_path = NULL WHERE image_path = :img"), {"img": image})
