"""«Дух Зверя»: Michael Olise up to 92 (admin's call). His and João Neves'
pictures were swapped in 0303 — the files are fixed in place, the paths
stay. Neves stays 88 epic.

Revision ID: 0304
Revises: 0303
"""
from alembic import op
import sqlalchemy as sa

revision = "0304"
down_revision = "0303"
branch_labels = None
depends_on = None

IMAGE = "players/legendary/beast_olise.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE players SET rating = 92, attack_rating = 95, defense_rating = 47, updated_at = now() "
        "WHERE image_path = :img"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE players SET rating = 90, attack_rating = 93, defense_rating = 45, updated_at = now() "
        "WHERE image_path = :img"
    ), {"img": IMAGE})
