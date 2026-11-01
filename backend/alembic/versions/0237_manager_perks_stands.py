"""«Менеджер» monetization: stadium skins («stands») and champion poster
styles («poster») appended to GameConfig.manager_cosmetics (codes already
there are skipped, an admin's edits stay), and manager_clubs.perks — the
Stars passes «Помощник президента» / «Аналитика Pro» and their reminders.

Revision ID: 0237
Revises: 0236
Create Date: 2026-11-01
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0237"
down_revision: Union[str, None] = "0236"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = json.loads(r'''
[{"code": "stands_classic", "kind": "stands", "name": "Классика", "value": "classic", "coins": 0, "stars": 0}, {"code": "stands_banners", "kind": "stands", "name": "Баннеры", "value": "banners", "coins": 8000, "stars": 59}, {"code": "stands_flares", "kind": "stands", "name": "Файеры", "value": "flares", "coins": 0, "stars": 99}, {"code": "stands_lights", "kind": "stands", "name": "Световое шоу", "value": "lights", "coins": 0, "stars": 119}, {"code": "stands_confetti", "kind": "stands", "name": "Конфетти", "value": "confetti", "coins": 0, "stars": 129}, {"code": "stands_tifo", "kind": "stands", "name": "Тифо", "value": "tifo", "coins": 0, "stars": 149}, {"code": "poster_classic", "kind": "poster", "name": "Классика", "value": "classic", "coins": 0, "stars": 0}, {"code": "poster_neon", "kind": "poster", "name": "Неон", "value": "neon", "coins": 0, "stars": 79}, {"code": "poster_gold", "kind": "poster", "name": "Золото", "value": "gold", "coins": 0, "stars": 99}]
''')


def _items(bind):
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return None, []
    return row[0], row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")


def _save(bind, row_id, items) -> None:
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items, ensure_ascii=False), "id": row_id},
    )


def upgrade() -> None:
    op.add_column("manager_clubs", sa.Column("perks", sa.JSON(), nullable=True))
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
    if row_id is not None:
        codes = {i["code"] for i in NEW_ITEMS}
        _save(bind, row_id, [i for i in items if i.get("code") not in codes])
    op.drop_column("manager_clubs", "perks")
