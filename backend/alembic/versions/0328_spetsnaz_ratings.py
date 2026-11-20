"""«Спецназ»: Lahm 90 → 93, De Bruyne 91 → 92, Shovkovskyi 85 → 89
(admin's call); attack/defence move by the same amount. Rarities stay
(legendary, legendary, epic).

Revision ID: 0328
Revises: 0327
"""
from alembic import op
import sqlalchemy as sa

revision = "0328"
down_revision = "0327"
branch_labels = None
depends_on = None

# art, old rating, old attack, old defence, new rating, new attack, new defence
CHANGES = (
    ("players/legendary/spn_lahm.webp", 90, 82, 91, 93, 85, 94),
    ("players/legendary/spn_de_bruyne.webp", 91, 93, 65, 92, 94, 66),
    ("players/epic/spn_shovkovskyi.webp", 85, 50, 88, 89, 54, 92),
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
