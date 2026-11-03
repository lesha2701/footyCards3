"""New emblem effects (frost, embers, pulse, halo, champion stars) and symbols drawn as pictures (static/emblems/symbols/<key>.webp,
white silhouettes tinted with the club colour): «Менеджер» symbols appended
to the admin-editable GameConfig.manager_cosmetics (codes already there are
skipped, so an admin's own edits stay). The clubs' emblem items come from
club_emblem_service.DEFAULT_CATALOG on first use. The old emoji / hand-drawn
symbols are gone: every club that had or wore one gets the closest picture.

Revision ID: 0243
Revises: 0242
Create Date: 2026-11-03
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0243"
down_revision: Union[str, None] = "0242"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ITEMS = json.loads(r'''
[{"code": "symbol_img_star", "kind": "symbol", "name": "Звезда чемпиона", "value": "img_star", "coins": 0, "stars": 0}, {"code": "symbol_img_ball", "kind": "symbol", "name": "Мяч", "value": "img_ball", "coins": 0, "stars": 0}, {"code": "symbol_img_crown", "kind": "symbol", "name": "Корона королей", "value": "img_crown", "coins": 4000, "stars": 39}, {"code": "symbol_img_tower", "kind": "symbol", "name": "Башня", "value": "img_tower", "coins": 4000, "stars": 39}, {"code": "symbol_img_mountain", "kind": "symbol", "name": "Горы", "value": "img_mountain", "coins": 4000, "stars": 39}, {"code": "symbol_img_wave", "kind": "symbol", "name": "Волна", "value": "img_wave", "coins": 4000, "stars": 39}, {"code": "symbol_img_compass", "kind": "symbol", "name": "Компас", "value": "img_compass", "coins": 4000, "stars": 39}, {"code": "symbol_img_horseshoe", "kind": "symbol", "name": "Подкова", "value": "img_horseshoe", "coins": 4000, "stars": 39}, {"code": "symbol_img_anchor", "kind": "symbol", "name": "Якорь", "value": "img_anchor", "coins": 4000, "stars": 39}, {"code": "symbol_img_lightning", "kind": "symbol", "name": "Молния", "value": "img_lightning", "coins": 4000, "stars": 39}, {"code": "symbol_img_flame", "kind": "symbol", "name": "Пламя", "value": "img_flame", "coins": 4000, "stars": 39}, {"code": "symbol_img_oak", "kind": "symbol", "name": "Дуб", "value": "img_oak", "coins": 4000, "stars": 39}, {"code": "symbol_img_trident", "kind": "symbol", "name": "Трезубец", "value": "img_trident", "coins": 5000, "stars": 49}, {"code": "symbol_img_rose", "kind": "symbol", "name": "Роза", "value": "img_rose", "coins": 5000, "stars": 49}, {"code": "symbol_img_rocket", "kind": "symbol", "name": "Взлёт", "value": "img_rocket", "coins": 5000, "stars": 49}, {"code": "symbol_img_crossed_swords", "kind": "symbol", "name": "Дуэль", "value": "img_crossed_swords", "coins": 5000, "stars": 49}, {"code": "symbol_img_eagle", "kind": "symbol", "name": "Орёл", "value": "img_eagle", "coins": 5000, "stars": 49}, {"code": "symbol_img_bear", "kind": "symbol", "name": "Медведь", "value": "img_bear", "coins": 5000, "stars": 49}, {"code": "symbol_img_bull", "kind": "symbol", "name": "Бык", "value": "img_bull", "coins": 5000, "stars": 49}, {"code": "symbol_img_fox", "kind": "symbol", "name": "Лис", "value": "img_fox", "coins": 5000, "stars": 49}, {"code": "symbol_img_horse", "kind": "symbol", "name": "Конь", "value": "img_horse", "coins": 5000, "stars": 49}, {"code": "symbol_img_owl", "kind": "symbol", "name": "Сова", "value": "img_owl", "coins": 5000, "stars": 49}, {"code": "symbol_img_ram", "kind": "symbol", "name": "Овен", "value": "img_ram", "coins": 5000, "stars": 49}, {"code": "symbol_img_stag", "kind": "symbol", "name": "Олень", "value": "img_stag", "coins": 5000, "stars": 49}, {"code": "symbol_img_hawk", "kind": "symbol", "name": "Ястреб", "value": "img_hawk", "coins": 5000, "stars": 49}, {"code": "symbol_img_knight_helmet", "kind": "symbol", "name": "Рыцарский шлем", "value": "img_knight_helmet", "coins": 6000, "stars": 59}, {"code": "symbol_img_bison", "kind": "symbol", "name": "Бизон", "value": "img_bison", "coins": 6000, "stars": 59}, {"code": "symbol_img_boar", "kind": "symbol", "name": "Кабан", "value": "img_boar", "coins": 6000, "stars": 59}, {"code": "symbol_img_bat", "kind": "symbol", "name": "Летучая мышь", "value": "img_bat", "coins": 6000, "stars": 59}, {"code": "symbol_img_wolf", "kind": "symbol", "name": "Волк", "value": "img_wolf", "coins": 6000, "stars": 59}, {"code": "symbol_img_raven", "kind": "symbol", "name": "Ворон", "value": "img_raven", "coins": 6000, "stars": 59}, {"code": "symbol_img_cobra", "kind": "symbol", "name": "Кобра", "value": "img_cobra", "coins": 6000, "stars": 59}, {"code": "symbol_img_panther", "kind": "symbol", "name": "Пантера", "value": "img_panther", "coins": 6000, "stars": 59}, {"code": "symbol_img_rhino", "kind": "symbol", "name": "Носорог", "value": "img_rhino", "coins": 6000, "stars": 59}, {"code": "symbol_img_shark", "kind": "symbol", "name": "Акула", "value": "img_shark", "coins": 6000, "stars": 59}, {"code": "symbol_img_scorpion", "kind": "symbol", "name": "Скорпион", "value": "img_scorpion", "coins": 0, "stars": 79}, {"code": "symbol_img_crocodile", "kind": "symbol", "name": "Крокодил", "value": "img_crocodile", "coins": 0, "stars": 79}, {"code": "symbol_img_tiger", "kind": "symbol", "name": "Тигр", "value": "img_tiger", "coins": 0, "stars": 79}, {"code": "symbol_img_lion", "kind": "symbol", "name": "Лев", "value": "img_lion", "coins": 0, "stars": 79}, {"code": "symbol_img_winged_ball", "kind": "symbol", "name": "Мяч с крыльями", "value": "img_winged_ball", "coins": 0, "stars": 99}, {"code": "symbol_img_griffin", "kind": "symbol", "name": "Грифон", "value": "img_griffin", "coins": 0, "stars": 129}, {"code": "symbol_img_pegasus", "kind": "symbol", "name": "Пегас", "value": "img_pegasus", "coins": 0, "stars": 129}, {"code": "symbol_img_dragon", "kind": "symbol", "name": "Дракон", "value": "img_dragon", "coins": 0, "stars": 129}, {"code": "symbol_img_phoenix", "kind": "symbol", "name": "Феникс", "value": "img_phoenix", "coins": 0, "stars": 149}, {"code": "symbol_img_cerberus", "kind": "symbol", "name": "Цербер", "value": "img_cerberus", "coins": 0, "stars": 149}, {"code": "symbol_img_kraken", "kind": "symbol", "name": "Кракен", "value": "img_kraken", "coins": 0, "stars": 149}, {"code": "fx_frost", "kind": "fx", "name": "Иней", "value": "frost", "coins": 0, "stars": 129}, {"code": "fx_embers", "kind": "fx", "name": "Угли", "value": "embers", "coins": 0, "stars": 129}, {"code": "fx_pulse", "kind": "fx", "name": "Волна силы", "value": "pulse", "coins": 0, "stars": 149}, {"code": "fx_halo", "kind": "fx", "name": "Нимб", "value": "halo", "coins": 0, "stars": 149}, {"code": "fx_champion", "kind": "fx", "name": "Звёзды чемпиона", "value": "champion", "coins": 0, "stars": 199}]
''')


# The old symbols are replaced by the closest picture, owners keep what they paid for.
MANAGER_SWAP = {
    "⚽": "img_ball", "⭐": "img_star", "🦁": "img_lion", "🦅": "img_eagle", "🐺": "img_wolf",
    "🐻": "img_bear", "🐯": "img_tiger", "🐂": "img_bull", "🦈": "img_shark", "🐎": "img_horse",
    "⚓": "img_anchor", "⚡": "img_lightning", "🔥": "img_flame", "🚀": "img_rocket", "🐉": "img_dragon",
    "👑": "img_crown",
}
CLUB_SWAP = {
    "ball": "img_ball", "crown": "img_crown", "lion": "img_lion", "eagle": "img_eagle",
    "lightning": "img_lightning", "castle": "img_tower", "star": "img_star", "trophy": "img_star",
    "wings": "img_winged_ball", "anchor": "img_anchor", "wolf": "img_wolf", "swords": "img_crossed_swords",
}
# (style_key, name, stars) — the same rows club_emblem_service.DEFAULT_CATALOG has,
# inserted here so the swapped unlocks have something to point at.
CLUB_ITEMS = [
    ("img_star", "Звезда чемпиона", 75),
    ("img_ball", "Мяч", 75),
    ("img_crown", "Корона королей", 75),
    ("img_tower", "Башня", 75),
    ("img_mountain", "Горы", 75),
    ("img_wave", "Волна", 75),
    ("img_compass", "Компас", 75),
    ("img_horseshoe", "Подкова", 75),
    ("img_anchor", "Якорь", 75),
    ("img_lightning", "Молния", 75),
    ("img_flame", "Пламя", 75),
    ("img_oak", "Дуб", 75),
    ("img_trident", "Трезубец", 100),
    ("img_rose", "Роза", 100),
    ("img_rocket", "Взлёт", 100),
    ("img_crossed_swords", "Дуэль", 100),
    ("img_eagle", "Орёл", 100),
    ("img_bear", "Медведь", 100),
    ("img_bull", "Бык", 100),
    ("img_fox", "Лис", 100),
    ("img_horse", "Конь", 100),
    ("img_owl", "Сова", 100),
    ("img_ram", "Овен", 100),
    ("img_stag", "Олень", 100),
    ("img_hawk", "Ястреб", 100),
    ("img_knight_helmet", "Рыцарский шлем", 100),
    ("img_bison", "Бизон", 100),
    ("img_boar", "Кабан", 100),
    ("img_bat", "Летучая мышь", 100),
    ("img_wolf", "Волк", 100),
    ("img_raven", "Ворон", 100),
    ("img_cobra", "Кобра", 100),
    ("img_panther", "Пантера", 125),
    ("img_rhino", "Носорог", 125),
    ("img_shark", "Акула", 125),
    ("img_scorpion", "Скорпион", 125),
    ("img_crocodile", "Крокодил", 125),
    ("img_tiger", "Тигр", 125),
    ("img_lion", "Лев", 125),
    ("img_winged_ball", "Мяч с крыльями", 150),
    ("img_griffin", "Грифон", 150),
    ("img_pegasus", "Пегас", 150),
    ("img_dragon", "Дракон", 200),
    ("img_phoenix", "Феникс", 200),
    ("img_cerberus", "Цербер", 200),
    ("img_kraken", "Кракен", 200),
]


def _is_old_symbol(item) -> bool:
    return (isinstance(item, dict) and item.get("kind") == "symbol"
            and not str(item.get("value") or "").startswith("img_"))


def _save(bind, row_id, items) -> None:
    bind.execute(
        sa.text("UPDATE game_config SET manager_cosmetics = CAST(:items AS json) WHERE id = :id"),
        {"items": json.dumps(items, ensure_ascii=False), "id": row_id},
    )


def _upgrade_manager(bind) -> None:
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    have = {i.get("code") for i in items if isinstance(i, dict)}
    for old in (i for i in items if _is_old_symbol(i)):
        new = MANAGER_SWAP.get(old.get("value"), "img_star")
        params = {"old": old["code"], "new": f"symbol_{new}"}
        bind.execute(sa.text(
            "INSERT INTO manager_cosmetics (club_id, code, created_at) "
            "SELECT club_id, :new, created_at FROM manager_cosmetics WHERE code = :old "
            "ON CONFLICT (club_id, code) DO NOTHING"
        ), params)
        bind.execute(sa.text("DELETE FROM manager_cosmetics WHERE code = :old"), params)
    for club_id, look in bind.execute(sa.text("SELECT id, look FROM manager_clubs")).all():
        look = look if isinstance(look, dict) else json.loads(look or "{}")
        symbol = look.get("symbol")
        if symbol is not None and not str(symbol).startswith("img_"):
            bind.execute(sa.text("UPDATE manager_clubs SET look = CAST(:look AS json) WHERE id = :id"), {
                "look": json.dumps({**look, "symbol": MANAGER_SWAP.get(symbol, "img_star")}, ensure_ascii=False),
                "id": club_id,
            })
    items = [i for i in items if not _is_old_symbol(i)]
    _save(bind, row[0], items + [i for i in NEW_ITEMS if i["code"] not in have])


def _upgrade_clubs(bind) -> None:
    for order, (key, name, stars) in enumerate(CLUB_ITEMS):
        bind.execute(sa.text(
            "INSERT INTO club_emblem_items (kind, style_key, name, coins_price, stars_price, is_active, sort_order) "
            "VALUES ('symbol', :key, :name, 0, :stars, true, :order) "
            "ON CONFLICT (kind, style_key) DO UPDATE SET sort_order = EXCLUDED.sort_order"
        ), {"key": key, "name": name, "stars": stars, "order": 100 + order})
    for old, new in CLUB_SWAP.items():
        params = {"old": old, "new": new}
        bind.execute(sa.text(
            "INSERT INTO club_emblem_unlocks (club_id, item_id, source, user_id, created_at) "
            "SELECT u.club_id, n.id, u.source, u.user_id, u.created_at FROM club_emblem_unlocks u "
            "JOIN club_emblem_items o ON o.id = u.item_id AND o.kind = 'symbol' AND o.style_key = :old "
            "JOIN club_emblem_items n ON n.kind = 'symbol' AND n.style_key = :new "
            "ON CONFLICT (club_id, item_id) DO NOTHING"
        ), params)
        bind.execute(sa.text("UPDATE clubs SET logo_symbol = :new WHERE logo_symbol = :old"), params)
        # cascades to the old unlocks
        bind.execute(sa.text("DELETE FROM club_emblem_items WHERE kind = 'symbol' AND style_key = :old"), params)


def upgrade() -> None:
    bind = op.get_bind()
    _upgrade_manager(bind)
    _upgrade_clubs(bind)


def downgrade() -> None:
    # The swap is one-way: only the new «Менеджер» catalog rows are taken out.
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT id, manager_cosmetics FROM game_config ORDER BY id LIMIT 1")).first()
    if row is None:
        return
    items = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")
    codes = {i["code"] for i in NEW_ITEMS}
    _save(bind, row[0], [i for i in items if not isinstance(i, dict) or i.get("code") not in codes])
