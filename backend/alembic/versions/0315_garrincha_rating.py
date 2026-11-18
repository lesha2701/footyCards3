"""«Дух Зверя»: Garrincha 94 → 93 overall, attack 97 → 94 (admin's call).
Stays legendary.

Revision ID: 0315
Revises: 0314
"""
from alembic import op
import sqlalchemy as sa

revision = "0315"
down_revision = "0314"
branch_labels = None
depends_on = None

IMAGE = "players/legendary/beast_garrincha.webp"


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE players SET rating = 93, attack_rating = 94, updated_at = now() WHERE image_path = :img"
    ), {"img": IMAGE})


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "UPDATE players SET rating = 94, attack_rating = 97, updated_at = now() WHERE image_path = :img"
    ), {"img": IMAGE})
