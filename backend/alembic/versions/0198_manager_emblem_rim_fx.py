"""«Менеджер» emblem: new cosmetic kinds «Обводка эмблемы» (rim) and
«Эффект эмблемы» (fx) — appended to the admin-editable
GameConfig.manager_cosmetics, skipping codes already there, so an admin's
own edits stay.

Revision ID: 0198
Revises: 0197
Create Date: 2026-10-23
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0198"
down_revision: Union[str, None] = "0197"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = json.loads(r'''
[{"code": "rim_none", "kind": "rim", "name": "Без обводки", "value": "none", "coins": 0, "stars": 0}, {"code": "rim_bronze", "kind": "rim", "name": "Бронза", "value": "bronze", "coins": 6000, "stars": 39}, {"code": "rim_silver", "kind": "rim", "name": "Серебро", "value": "silver", "coins": 0, "stars": 59}, {"code": "rim_gold", "kind": "rim", "name": "Золото", "value": "gold", "coins": 0, "stars": 99}, {"code": "rim_ruby", "kind": "rim", "name": "Рубин", "value": "ruby", "coins": 0, "stars": 99}, {"code": "rim_emerald", "kind": "rim", "name": "Изумруд", "value": "emerald", "coins": 0, "stars": 99}, {"code": "rim_neon", "kind": "rim", "name": "Неон", "value": "neon", "coins": 0, "stars": 129}, {"code": "rim_diamond", "kind": "rim", "name": "Бриллиант", "value": "diamond", "coins": 0, "stars": 149}, {"code": "rim_rainbow", "kind": "rim", "name": "Радуга", "value": "rainbow", "coins": 0, "stars": 199}, {"code": "fx_none", "kind": "fx", "name": "Без эффекта", "value": "none", "coins": 0, "stars": 0}, {"code": "fx_shine", "kind": "fx", "name": "Блеск", "value": "shine", "coins": 0, "stars": 99}, {"code": "fx_sparkle", "kind": "fx", "name": "Мерцание", "value": "sparkle", "coins": 0, "stars": 99}, {"code": "fx_flame", "kind": "fx", "name": "Пламя", "value": "flame", "coins": 0, "stars": 129}, {"code": "fx_aura", "kind": "fx", "name": "Аура", "value": "aura", "coins": 0, "stars": 129}, {"code": "fx_laurel", "kind": "fx", "name": "Лавровый венок", "value": "laurel", "coins": 0, "stars": 149}, {"code": "fx_rays", "kind": "fx", "name": "Сияние", "value": "rays", "coins": 0, "stars": 149}, {"code": "fx_orbit", "kind": "fx", "name": "Мяч на орбите", "value": "orbit", "coins": 0, "stars": 149}, {"code": "fx_lightning", "kind": "fx", "name": "Молнии", "value": "lightning", "coins": 0, "stars": 199}]
''')


def upgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    have = {i.get("code") for i in items if isinstance(i, dict)}
    added = [i for i in NEW_ITEMS if i["code"] not in have]
    if not added:
        return
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items + added, ensure_ascii=False), "id": row[0]},
    )


def downgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    codes = {i["code"] for i in NEW_ITEMS}
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps([i for i in items if i.get("code") not in codes], ensure_ascii=False), "id": row[0]},
    )
