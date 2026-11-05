"""Lion and hawk picture symbols for the clubs' emblems and «Менеджер» (for
databases that already ran 0243 before they were added there; a no-op
otherwise).

Revision ID: 0244
Revises: 0243
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0244"
down_revision: Union[str, None] = "0243"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = [
    {"code": "symbol_img_hawk", "kind": "symbol", "name": "Ястреб", "value": "img_hawk", "coins": 5000, "stars": 49},
    {"code": "symbol_img_lion", "kind": "symbol", "name": "Лев", "value": "img_lion", "coins": 0, "stars": 79},
]
CLUB_ITEMS = [("img_hawk", "Ястреб", 100), ("img_lion", "Лев", 125)]


def upgrade() -> None:
    bind = op.get_bind()
    for key, name, stars in CLUB_ITEMS:
        bind.execute(sa.text(
            "INSERT INTO club_emblem_items (kind, style_key, name, coins_price, stars_price, is_active, sort_order) "
            "VALUES ('symbol', :key, :name, 0, :stars, true, "
            "(SELECT COALESCE(MAX(sort_order), 0) + 1 FROM club_emblem_items WHERE kind = 'symbol' AND stars_price <= :stars)) "
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
    pass  # 0243 owns these rows on a fresh database
