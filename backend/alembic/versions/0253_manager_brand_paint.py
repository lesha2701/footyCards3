"""«Особый цвет эмблемы» in «Менеджер»: the Victor FC gradient (turquoise → green
→ lime) for 99 Stars and «Лимонный» (top to bottom into lemon) for 9 Stars as the emblem's main colour.

Revision ID: 0253
Revises: 0252
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0253"
down_revision: Union[str, None] = "0252"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = [
    {"code": "paint_brand", "kind": "paint", "name": "Градиент Victor", "value": "brand", "coins": 0, "stars": 99},
    {"code": "paint_lemon", "kind": "paint", "name": "Лимонный", "value": "lemon", "coins": 0, "stars": 9},
]


def _items(bind):
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return None, []
    return row[0], row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")


def _save(bind, row_id, items):
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items, ensure_ascii=False), "id": row_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    row_id, items = _items(bind)
    if row_id is None:
        return
    have = {i.get("code") for i in items if isinstance(i, dict)}
    added = [i for i in NEW_ITEMS if i["code"] not in have]
    if added:
        _save(bind, row_id, items + added)


def downgrade() -> None:
    bind = op.get_bind()
    row_id, items = _items(bind)
    if row_id is None:
        return
    codes = {i["code"] for i in NEW_ITEMS}
    _save(bind, row_id, [i for i in items if not isinstance(i, dict) or i.get("code") not in codes])
