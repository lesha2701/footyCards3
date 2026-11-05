"""«Дьявол» (the devil head symbol) for 66 Stars instead of 166, in «Менеджер»
and the clubs' emblem builder.

Revision ID: 0250
Revises: 0249
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0250"
down_revision: Union[str, None] = "0249"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _set(stars: int) -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE club_emblem_items SET stars_price = :stars WHERE kind = 'symbol' AND style_key = 'img_devil'"
    ), {"stars": stars})
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    items = [{**i, "stars": stars} if isinstance(i, dict) and i.get("code") == "symbol_img_devil" else i for i in items]
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items, ensure_ascii=False), "id": row[0]},
    )


def upgrade() -> None:
    _set(66)


def downgrade() -> None:
    _set(166)
