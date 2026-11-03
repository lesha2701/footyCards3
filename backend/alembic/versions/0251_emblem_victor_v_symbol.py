"""The «V» of the Victor FC crest as a picture symbol (999 Stars) for the clubs'
emblems and «Менеджер».

Revision ID: 0251
Revises: 0250
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0251"
down_revision: Union[str, None] = "0250"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STARS = 999
NEW_ITEMS = [
    {"code": "symbol_img_victor_v", "kind": "symbol", "name": "Знак Victor", "value": "img_victor_v", "coins": 0, "stars": STARS},
]
CLUB_ITEMS = [("img_victor_v", "Знак Victor")]


def upgrade() -> None:
    bind = op.get_bind()
    for key, name in CLUB_ITEMS:
        bind.execute(sa.text(
            "INSERT INTO club_emblem_items (kind, style_key, name, coins_price, stars_price, is_active, sort_order) "
            "VALUES ('symbol', :key, :name, 0, :stars, true, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM club_emblem_items WHERE kind = 'symbol')) "
            "ON CONFLICT (kind, style_key) DO NOTHING"
        ), {"key": key, "name": name, "stars": STARS})
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
    bind.execute(sa.text("DELETE FROM club_emblem_items WHERE kind = 'symbol' AND style_key = 'img_victor_v'"))
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
