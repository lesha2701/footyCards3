"""«Лига чемпионов»: Shakhtar ratings raised above the EA FC 27 launch values
(admin's call — a Champions League edition). Rarity follows the rating
(90+ legendary, 85–89 epic, 80–84 rare, below 80 common); five cards move
to rare, so their art moved to static/players/rare/ and the sell price
follows the rarity. Owned copies change with the design.

Revision ID: 0282
Revises: 0281
"""
from alembic import op
import sqlalchemy as sa

revision = "0282"
down_revision = "0281"
branch_labels = None
depends_on = None

SELL_PRICE = {"common": 10, "rare": 35, "epic": 120, "legendary": 400}

# art slug, old rating, old attack, old defence, old rarity, new rating, new attack, new defence, new rarity
CHANGES = (
    ("riznyk", 74, 45, 77, "common", 82, 53, 85, "rare"),
    ("tobias", 71, 68, 70, "common", 78, 75, 77, "common"),
    ("bondar", 75, 55, 78, "common", 81, 61, 84, "rare"),
    ("matviienko", 77, 60, 80, "common", 83, 66, 86, "rare"),
    ("pedro_henrique", 72, 68, 70, "common", 80, 76, 78, "rare"),
    ("nazaryna", 69, 67, 66, "common", 77, 75, 74, "common"),
    ("alisson_santana", 70, 75, 38, "common", 79, 84, 47, "common"),
    ("ocheretko", 66, 70, 55, "common", 76, 80, 65, "common"),
    ("marlon_gomes", 70, 70, 66, "common", 79, 79, 75, "common"),
    ("mendoza", 65, 70, 35, "common", 75, 80, 45, "common"),
    ("kaua_elias", 71, 76, 38, "common", 80, 85, 47, "rare"),
    ("newerton", 70, 75, 38, "common", 78, 83, 46, "common"),
    ("isaque", 66, 71, 50, "common", 75, 80, 59, "common"),
    ("traore", 71, 76, 40, "common", 79, 84, 48, "common"),
    ("lucas_ferreira", 67, 72, 38, "common", 76, 81, 47, "common"),
    ("meirelles", 66, 72, 36, "common", 75, 81, 45, "common"),
)


def _apply(conn, slug, rating, attack, defence, old_rarity, rarity):
    conn.execute(sa.text(
        "UPDATE players SET rating = :r, attack_rating = :a, defense_rating = :d, "
        "rarity = CAST(:rarity AS rarity_enum), image_path = :img, quick_sell_price = :sell, updated_at = now() "
        "WHERE image_path = :old_img"
    ), {
        "r": rating, "a": attack, "d": defence, "rarity": rarity, "sell": SELL_PRICE[rarity],
        "img": f"players/{rarity}/ucl_shk_{slug}.webp", "old_img": f"players/{old_rarity}/ucl_shk_{slug}.webp",
    })


def upgrade() -> None:
    conn = op.get_bind()
    for slug, _r, _a, _d, old_rarity, rating, attack, defence, rarity in CHANGES:
        _apply(conn, slug, rating, attack, defence, old_rarity, rarity)


def downgrade() -> None:
    conn = op.get_bind()
    for slug, rating, attack, defence, rarity, _r, _a, _d, new_rarity in CHANGES:
        _apply(conn, slug, rating, attack, defence, new_rarity, rarity)
