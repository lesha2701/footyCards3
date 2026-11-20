"""«Замес»: hero skins for Stars — cosmetics kind "zames_hero" (style only),
the users' equipped slot and the five skins.

Revision ID: 0325
Revises: 0324
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0325"
down_revision: Union[str, None] = "0324"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ck_cosmetics_kind (0194, 0298) lists every allowed kind.
KINDS_BEFORE = (
    "'profile_frame', 'profile_background', 'card_skin', 'brutality', 'ring_gloves', 'ring_shorts', "
    "'ring_entrance', 'helmet', 'magic_hero', 'magic_castle'"
)
KINDS_AFTER = KINDS_BEFORE + ", 'zames_hero'"
# style_key = the rig the game draws (frontend assets/zames/rig/skin-<key>-*.webp).
SKINS = (
    ("Ультрас", "Панама, ветровка под горло и шарф с молниями", "ultras", 25, 1),
    ("Дед с термосом", "Кепка, вязаный кардиган, термос и шарф до колен", "ded", 25, 2),
    ("Маскот-лев", "Плюшевый костюм льва с гривой и хвостом", "mascot", 40, 3),
    ("Викинг", "Рогатый шлем, рыжая борода и шарф вместо пояса", "viking", 50, 4),
    ("Золотой", "Золотой костюм, капитанская фуражка и очки", "gold", 75, 5),
)


def upgrade() -> None:
    op.add_column("users", sa.Column(
        "equipped_zames_hero_id", sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True,
    ))
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_AFTER})")
    cosmetics = sa.table(
        "cosmetics", sa.column("kind", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("style_key", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("sort_order", sa.Integer), sa.column("is_exclusive", sa.Boolean),
    )
    op.bulk_insert(cosmetics, [
        {"kind": "zames_hero", "name": n, "description": d, "style_key": key, "coins_price": 0, "stars_price": st,
         "sort_order": o, "is_exclusive": False}
        for n, d, key, st, o in SKINS
    ])


def downgrade() -> None:
    op.drop_column("users", "equipped_zames_hero_id")
    op.execute("DELETE FROM user_cosmetics WHERE cosmetic_id IN (SELECT id FROM cosmetics WHERE kind = 'zames_hero')")
    op.execute("DELETE FROM cosmetics WHERE kind = 'zames_hero'")
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_BEFORE})")
