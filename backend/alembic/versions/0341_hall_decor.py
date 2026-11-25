"""«Зал славы» — «Обустроить зал»: cosmetics kinds for the hall's places
(cabinet / pedestal skins, floor / wall / front decor), the owner's layout
and the first skins. Prices are ordinary `cosmetics` rows, edited in the
admin panel.

Revision ID: 0341
Revises: 0340
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0341"
down_revision: Union[str, None] = "0340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ck_cosmetics_kind (0194, 0298, 0325) lists every allowed kind.
KINDS_BEFORE = (
    "'profile_frame', 'profile_background', 'card_skin', 'brutality', 'ring_gloves', 'ring_shorts', "
    "'ring_entrance', 'helmet', 'magic_hero', 'magic_castle', 'zames_hero'"
)
HALL_KINDS = "'hall_cabinet', 'hall_pedestal', 'hall_floor', 'hall_wall', 'hall_front'"
KINDS_AFTER = KINDS_BEFORE + ", " + HALL_KINDS
# style_key = the art (frontend assets/hall/pedestal_<key>.webp). The niche
# skins come with their art later (kind hall_cabinet, assets/hall/niche_<key>).
# (kind, name, description, style_key, coins, stars, order)
SKINS = (
    ("hall_pedestal", "Дубовые постаменты", "Резной дуб с латунью", "oak", 10000, 0, 1),
    ("hall_pedestal", "Хрустальные постаменты", "Гранёный хрусталь", "crystal", 0, 35, 2),
    ("hall_pedestal", "Неоновые постаменты", "Чёрный мрамор с подсветкой", "neon", 0, 50, 3),
)


def upgrade() -> None:
    op.add_column("users", sa.Column("hall_layout", sa.JSON(), nullable=True))
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_AFTER})")
    cosmetics = sa.table(
        "cosmetics", sa.column("kind", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("style_key", sa.String), sa.column("coins_price", sa.Integer), sa.column("stars_price", sa.Integer),
        sa.column("sort_order", sa.Integer), sa.column("is_exclusive", sa.Boolean),
    )
    op.bulk_insert(cosmetics, [
        {"kind": k, "name": n, "description": d, "style_key": key, "coins_price": c, "stars_price": st,
         "sort_order": o, "is_exclusive": False}
        for k, n, d, key, c, st, o in SKINS
    ])


def downgrade() -> None:
    op.drop_column("users", "hall_layout")
    op.execute(f"DELETE FROM user_cosmetics WHERE cosmetic_id IN (SELECT id FROM cosmetics WHERE kind IN ({HALL_KINDS}))")
    op.execute(f"DELETE FROM cosmetics WHERE kind IN ({HALL_KINDS})")
    op.drop_constraint("ck_cosmetics_kind", "cosmetics", type_="check")
    op.create_check_constraint("ck_cosmetics_kind", "cosmetics", f"kind IN ({KINDS_BEFORE})")
