"""«Чемпион карьеры»: its own coach cup (static/trophies/career_champion_coach.webp)
instead of the tie cup 0306 set, which «Лучший президент» already uses. An
image an admin uploaded stays.

Revision ID: 0307
Revises: 0306
Create Date: 2026-11-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0307"
down_revision: Union[str, None] = "0306"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "trophies/career_champion.webp"
NEW = "trophies/career_champion_coach.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE trophy_definitions SET image_path = :new "
        "WHERE code = 'career_champion' AND (image_path IS NULL OR image_path = :old)"
    ), {"new": NEW, "old": OLD})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE trophy_definitions SET image_path = :old WHERE image_path = :new"), {"old": OLD, "new": NEW})
