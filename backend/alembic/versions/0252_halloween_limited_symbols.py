"""«🎃 Ночь тыкв» limited picture symbols for the clubs' emblems and «Менеджер»:
on sale only while the event runs (event_symbols.EVENT_SYMBOLS).

Revision ID: 0252
Revises: 0251
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0252"
down_revision: Union[str, None] = "0251"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = [
    {"code": "symbol_img_jack_o_lantern", "kind": "symbol", "name": "Тыква-фонарь", "value": "img_jack_o_lantern", "coins": 0, "stars": 49},
    {"code": "symbol_img_hw_bat", "kind": "symbol", "name": "Ночная мышь", "value": "img_hw_bat", "coins": 0, "stars": 49},
    {"code": "symbol_img_witch_hat", "kind": "symbol", "name": "Шляпа ведьмы", "value": "img_witch_hat", "coins": 0, "stars": 49},
    {"code": "symbol_img_ghost_keeper", "kind": "symbol", "name": "Призрак-вратарь", "value": "img_ghost_keeper", "coins": 0, "stars": 79},
    {"code": "symbol_img_skull_ball", "kind": "symbol", "name": "Череп-мяч", "value": "img_skull_ball", "coins": 0, "stars": 99},
    {"code": "symbol_img_reaper", "kind": "symbol", "name": "Жнец", "value": "img_reaper", "coins": 0, "stars": 149},
]
CLUB_ITEMS = [(i["value"], i["name"], i["stars"]) for i in NEW_ITEMS]


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, stars in CLUB_ITEMS:
        bind.execute(sa.text(
            "INSERT INTO club_emblem_items (kind, style_key, name, coins_price, stars_price, is_active, sort_order) "
            "VALUES ('symbol', :key, :name, 0, :stars, true, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM club_emblem_items WHERE kind = 'symbol')) "
            "ON CONFLICT (kind, style_key) DO NOTHING"
        ), {"key": key, "name": name, "stars": stars})
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    have = {i.get("code") for i in items if isinstance(i, dict)}
    added = [i for i in NEW_ITEMS if i["code"] not in have]
    if added:
        bind.execute(
            sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
            {"items": json.dumps(items + added, ensure_ascii=False), "id": row[0]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM club_emblem_items WHERE kind = 'symbol' AND style_key IN :keys").bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": [key for key, _, _ in CLUB_ITEMS]})
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    codes = {i["code"] for i in NEW_ITEMS}
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps([i for i in items if not isinstance(i, dict) or i.get("code") not in codes], ensure_ascii=False),
         "id": row[0]},
    )
