"""Three more kit patterns for «Менеджер» (contrast sleeves, chest band, yoke),
appended to the admin-editable GameConfig.manager_cosmetics (codes already
there are skipped).

Revision ID: 0245
Revises: 0244
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0245"
down_revision: Union[str, None] = "0244"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = [
    {"code": "kit_sleeves", "kind": "kit", "name": "Цветные рукава", "value": "sleeves", "coins": 4000, "stars": 39},
    {"code": "kit_band", "kind": "kit", "name": "Пояс", "value": "band", "coins": 4000, "stars": 39},
    {"code": "kit_yoke", "kind": "kit", "name": "Кокетка", "value": "yoke", "coins": 5000, "stars": 49},
]


def _rows(bind):
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return None, []
    return row[0], (row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]"))


def _save(bind, row_id, items) -> None:
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items, ensure_ascii=False), "id": row_id},
    )


def upgrade() -> None:
    bind = op.get_bind()
    row_id, items = _rows(bind)
    if row_id is None:
        return
    have = {i.get("code") for i in items if isinstance(i, dict)}
    added = [i for i in NEW_ITEMS if i["code"] not in have]
    if added:
        _save(bind, row_id, items + added)


def downgrade() -> None:
    bind = op.get_bind()
    row_id, items = _rows(bind)
    if row_id is None:
        return
    codes = {i["code"] for i in NEW_ITEMS}
    _save(bind, row_id, [i for i in items if not isinstance(i, dict) or i.get("code") not in codes])
