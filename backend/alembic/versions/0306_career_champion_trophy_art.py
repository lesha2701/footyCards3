"""«Чемпион карьеры» trophy art (static/trophies/career_champion.webp) — only
when an admin hasn't uploaded one already.

Revision ID: 0306
Revises: 0305
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0306"
down_revision: Union[str, None] = "0305"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IMAGE = "trophies/career_champion.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE trophy_definitions SET image_path = :img WHERE code = 'career_champion' AND image_path IS NULL"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE trophy_definitions SET image_path = NULL WHERE image_path = :img"), {"img": IMAGE})
