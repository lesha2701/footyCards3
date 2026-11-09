"""«Город»: dearer houses, places, hotel and «Жители» pack, less rent, rent
waits at most 12 hours (a visit 2–3 times a day). Only values the admin has
not changed since 0267 are rewritten.

Revision ID: 0270
Revises: 0269
Create Date: 2026-11-09
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0270"
down_revision: Union[str, None] = "0269"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_DISTRICTS = {
    "favela": {"price": 1000, "rent": 15}, "center": {"price": 2000, "rent": 25},
    "mountains": {"price": 3000, "rent": 35}, "beach": {"price": 4000, "rent": 45},
    "business": {"price": 6000, "rent": 60},
}
NEW_DISTRICTS = {
    "favela": {"price": 1500, "rent": 10}, "center": {"price": 3000, "rent": 18},
    "mountains": {"price": 4500, "rent": 25}, "beach": {"price": 6000, "rent": 32},
    "business": {"price": 9000, "rent": 42},
}
OLD_DECOR = {"pier": {"price": 20000, "rent_pct": 5}, "park": {"price": 40000, "rent_pct": 8},
             "island": {"price": 75000, "rent_pct": 12}}
NEW_DECOR = {"pier": {"price": 30000, "rent_pct": 5}, "park": {"price": 60000, "rent_pct": 8},
             "island": {"price": 110000, "rent_pct": 12}}
# column: (old default, new default)
NUMBERS = {
    "town_income_max_hours": (24, 12),
    "town_hotel_price": (5000, 8000),
    "town_hotel_rent_per_100_cards": (30, 20),
    "town_resident_max_daily_coins": (500, 200),
}
PACK = ("residents", 1000, 1500)


def _swap(old: dict, new: dict, current) -> dict:
    """Per entry: the new value only where the admin kept the old one."""
    current = current if isinstance(current, dict) else json.loads(current or "{}")
    out = dict(current)
    for code, values in new.items():
        if current.get(code) in (None, old[code]):
            out[code] = values
    return out


def _move(direction: int) -> None:
    conn = op.get_bind()
    row = conn.execute(sa.text("SELECT town_districts, town_decor FROM game_config WHERE id = 1")).first()
    if row is not None:
        districts = (OLD_DISTRICTS, NEW_DISTRICTS)[::direction]
        decor = (OLD_DECOR, NEW_DECOR)[::direction]
        conn.execute(sa.text("UPDATE game_config SET town_districts = :d, town_decor = :p WHERE id = 1"), {
            "d": json.dumps(_swap(districts[0], districts[1], row[0])),
            "p": json.dumps(_swap(decor[0], decor[1], row[1])),
        })
        for column, (old, new) in NUMBERS.items():
            frm, to = (old, new)[::direction]
            conn.execute(sa.text(f"UPDATE game_config SET {column} = :to WHERE id = 1 AND {column} = :frm"),
                         {"to": to, "frm": frm})
    slug, old_price, new_price = PACK
    frm, to = (old_price, new_price)[::direction]
    conn.execute(sa.text("UPDATE packs SET price = :to WHERE slug = :slug AND price = :frm"),
                 {"to": to, "frm": frm, "slug": slug})


def upgrade() -> None:
    _move(1)


def downgrade() -> None:
    _move(-1)
