"""«Дух Зверя»: Ronaldinho 93 → 95 and Lev Yashin 91 → 95 (admin's call);
attack/defence move by the same amount. Both stay legendary.

Revision ID: 0305
Revises: 0304
"""
from alembic import op
import sqlalchemy as sa

revision = "0305"
down_revision = "0304"
branch_labels = None
depends_on = None

# art, old rating, old attack, old defence, new rating, new attack, new defence
CHANGES = (
    ("players/legendary/beast_ronaldinho.webp", 93, 96, 50, 95, 98, 52),
    ("players/legendary/beast_yashin.webp", 91, 55, 94, 95, 59, 98),
)


def _set(rating: int, attack: int, defence: int, image: str) -> None:
    op.get_bind().execute(sa.text(
        "UPDATE players SET rating = :r, attack_rating = :a, defense_rating = :d, updated_at = now() "
        "WHERE image_path = :img"
    ), {"r": rating, "a": attack, "d": defence, "img": image})


def upgrade() -> None:
    for image, _r, _a, _d, rating, attack, defence in CHANGES:
        _set(rating, attack, defence, image)


def downgrade() -> None:
    for image, rating, attack, defence, *_ in CHANGES:
        _set(rating, attack, defence, image)
