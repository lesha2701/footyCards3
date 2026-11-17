"""«Город»: houses ~10% dearer and rent ~10% lower in every district; the
first «Наборы жителей» (by resident name, only where the admin left the set
empty).

Revision ID: 0278
Revises: 0277
Create Date: 2026-11-10
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0278"
down_revision: Union[str, None] = "0277"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = {
    "favela": {"price": 1500, "rent": 10}, "residential": {"price": 2200, "rent": 14},
    "center": {"price": 3000, "rent": 18}, "mountains": {"price": 4500, "rent": 25},
    "beach": {"price": 6000, "rent": 32}, "industrial": {"price": 7500, "rent": 36},
    "business": {"price": 9000, "rent": 42}, "airport": {"price": 11000, "rent": 50},
    "island": {"price": 14000, "rent": 60},
}
NEW = {
    "favela": {"price": 1700, "rent": 9}, "residential": {"price": 2400, "rent": 13},
    "center": {"price": 3300, "rent": 16}, "mountains": {"price": 5000, "rent": 23},
    "beach": {"price": 6600, "rent": 29}, "industrial": {"price": 8300, "rent": 33},
    "business": {"price": 9900, "rent": 38}, "airport": {"price": 12100, "rent": 45},
    "island": {"price": 15400, "rent": 54},
}
SETS = {
    "Звёзды клуба": ("Мариана", "Томаш", "Нуну", "Лео"),
    "Пляжная банда": ("Бьянка", "Жозе", "Лусия", "Роза"),
    "Португальская сборная": ("Аугушту", "Энрике", "Дуарте", "Матилде"),
}


def _swap(old: dict, new: dict, current) -> dict:
    """Per district: the new values only where the admin kept the old ones
    (a district missing from the row takes the code default)."""
    current = current if isinstance(current, dict) else json.loads(current or "{}")
    out = dict(current)
    for code, values in new.items():
        if code in current and current[code] == old[code]:
            out[code] = values
    return out


def _move(old: dict, new: dict) -> None:
    conn = op.get_bind()
    row = conn.execute(sa.text("SELECT town_districts FROM game_config WHERE id = 1")).first()
    if row is not None:
        conn.execute(sa.text("UPDATE game_config SET town_districts = :d WHERE id = 1"),
                     {"d": json.dumps(_swap(old, new, row[0]))})


def upgrade() -> None:
    _move(OLD, NEW)
    conn = op.get_bind()
    for set_name, names in SETS.items():
        for name in names:
            conn.execute(sa.text(
                "UPDATE town_residents SET set_name = :s WHERE name = :n AND is_active AND set_name IS NULL"
            ), {"s": set_name, "n": name})


def downgrade() -> None:
    _move(NEW, OLD)
    conn = op.get_bind()
    for set_name in SETS:
        conn.execute(sa.text("UPDATE town_residents SET set_name = NULL WHERE set_name = :s"), {"s": set_name})
