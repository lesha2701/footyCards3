"""Symbol prices: ball, tower, lightning and compass for 2000 coins, every
other picture symbol for Stars only — in «Менеджер» and the clubs' emblem
builder. «Менеджер» gets a free «Без символа» (the new default); a club that
wears a symbol which was free so far (the ball by default, the star) is given
it for good.

Revision ID: 0246
Revises: 0245
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0246"
down_revision: Union[str, None] = "0245"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COIN_SYMBOLS = {"img_ball", "img_tower", "img_lightning", "img_compass"}
COINS = 2000
STAR_PRICE_IF_FREE = 39  # «Звезда чемпиона» was free
NONE_ITEM = {"code": "symbol_none", "kind": "symbol", "name": "Без символа", "value": "none", "coins": 0, "stars": 0}
WAS_FREE = {"img_ball": "symbol_img_ball", "img_star": "symbol_img_star"}


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE club_emblem_items SET coins_price = :coins, stars_price = 0 "
        "WHERE kind = 'symbol' AND style_key IN :keys"
    ).bindparams(sa.bindparam("keys", expanding=True)), {"coins": COINS, "keys": sorted(COIN_SYMBOLS)})

    # Whoever wears a so-far free symbol keeps it (an empty look meant the ball).
    for club_id, look in bind.execute(sa.text("SELECT id, look FROM manager_clubs")).all():
        look = look if isinstance(look, dict) else json.loads(look or "{}")
        symbol = look.get("symbol") or "img_ball"
        if symbol in WAS_FREE:
            bind.execute(sa.text(
                "INSERT INTO manager_cosmetics (club_id, code, created_at) VALUES (:c, :code, now()) "
                "ON CONFLICT (club_id, code) DO NOTHING"
            ), {"c": club_id, "code": WAS_FREE[symbol]})
            if "symbol" not in look:
                bind.execute(sa.text("UPDATE manager_clubs SET look = CAST(:look AS json) WHERE id = :id"),
                             {"look": json.dumps({**look, "symbol": symbol}, ensure_ascii=False), "id": club_id})

    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    out = []
    for i in items:
        if isinstance(i, dict) and i.get("kind") == "symbol" and str(i.get("value") or "").startswith("img_"):
            if i["value"] in COIN_SYMBOLS:
                i = {**i, "coins": COINS, "stars": 0}
            else:
                i = {**i, "coins": 0, "stars": i.get("stars") or STAR_PRICE_IF_FREE}
        out.append(i)
    if not any(isinstance(i, dict) and i.get("code") == NONE_ITEM["code"] for i in out):
        first = next((n for n, i in enumerate(out) if isinstance(i, dict) and i.get("kind") == "symbol"), len(out))
        out.insert(first, NONE_ITEM)
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(out, ensure_ascii=False), "id": row[0]},
    )


def downgrade() -> None:
    pass  # prices are the admin's from here on
