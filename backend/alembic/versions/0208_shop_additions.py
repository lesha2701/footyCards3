"""New shop goods, and what they need:
- coin_packages.bonus_pct («+15%» label) — 5 750 coins for 49⭐, 150 000 for 999⭐;
- packs.daily_limit_per_user — «Легенда дня»: one legendary card, 49⭐, once a day;
- user_equipment.binds_on_equip / bound_card_id — a thing bought with coins
  belongs to the first card it is put on (off and on again, never on another
  card; goes with the card in a trade, deleted with it); the «Дерби» set;
- three Stars-only artifacts, four lifestyle items;
- gift_sets.pack_count — the «Сундук чемпиона» opens two packs; three gifts;
- four cosmetics (one Stars-only).
Prices and effects are edited in the admin afterwards.

Revision ID: 0208
Revises: 0207
Create Date: 2026-10-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0208"
down_revision: Union[str, None] = "0207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARTIFACTS = [
    # name, description, icon, rarity, target, effect, value, stars, status
    ("Свисток Коллины", "Свисток самого строгого арбитра в истории.", "🟨", "legendary", "club", "opp_home_pct", 1, 199, 35),
    ("Бутсы Роналдиньо", "В них улыбка не сходила с лица — и защитники падали.", "👟", "legendary", "my_player", "dribble_pp", 3, 300, 40),
    ("Реплика Кубка Либертадорес", "Самый тяжёлый трофей Южной Америки.", "🏆", "epic", "my_player", "match_rating", 2, 150, 25),
]
LIFESTYLE = [
    # name, description, category, emoji, coins, stars, prestige, effect, value
    ("Самокат", "Быстро до тренировочной базы.", "car", "🛴", 800, 0, 5, "none", 0),
    ("Кофейня у стадиона", "Болельщики идут за кофе перед матчем.", "estate", "☕", 10000, 0, 40, "weekly_income", 800),
    ("Футбольная школа", "Своя академия для детей района.", "other", "🏫", 20000, 0, 60, "xp_bonus_pct", 5),
    ("Яхта", "Отпуск между сезонами — только так.", "other", "🛥️", 0, 400, 180, "xp_bonus_pct", 8),
]
DERBY = [
    # name, slot, icon, effect, value, coins, stars
    ("Бутсы «Дерби»", "boots", "👟", "shot_pp", 4, 5000, 50),
    ("Форма «Дерби»", "kit", "👕", "rating", 1, 6000, 60),
    ("Гетры «Дерби»", "socks", "🧦", "tackle_pp", 4, 4000, 40),
    ("Перчатки «Дерби»", "gloves", "🧤", "save_pp", 4, 5000, 50),
    ("Шарф «Дерби»", "accessory", "🧣", "coins_pct", 10, 7000, 70),
]
COSMETICS = [
    # kind, name, style_key, coins, stars
    ("profile_background", "Северное сияние", "aurora", 8000, 60),
    ("profile_background", "Дерби", "derby", 10000, 75),
    ("card_skin", "Скин «Золото»", "gold", 12000, 90),
    ("profile_frame", "Рамка «Ультрас»", "ultras", 0, 149),
]


def upgrade() -> None:
    conn = op.get_bind()
    op.add_column("coin_packages", sa.Column("bonus_pct", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("packs", sa.Column("daily_limit_per_user", sa.Integer(), nullable=True))
    op.add_column("user_equipment", sa.Column("binds_on_equip", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_equipment", sa.Column(
        "bound_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="CASCADE"), nullable=True,
    ))
    op.create_index("ix_user_equipment_bound_card_id", "user_equipment", ["bound_card_id"])
    op.add_column("gift_sets", sa.Column("pack_count", sa.Integer(), nullable=False, server_default="1"))

    for coins, stars, bonus, sort in ((5750, 49, 15, 25), (150000, 999, 50, 90)):
        conn.execute(sa.text(
            "INSERT INTO coin_packages (stars_price, coins_amount, bonus_pct, is_active, sort_order, created_at, updated_at) "
            "VALUES (:stars, :coins, :bonus, true, :sort, now(), now())"
        ), {"stars": stars, "coins": coins, "bonus": bonus, "sort": sort})

    pack_id = conn.execute(sa.text(
        "INSERT INTO packs (slug, name, description, price, stars_price, card_count, guaranteed_min_rarity, is_active, "
        "daily_limit_per_user, sort_order, coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, "
        "player_pool, muse_drop_chance, created_at, updated_at) "
        "VALUES ('daily-legend', 'Легенда дня', 'Одна легендарная карта. Открывается раз в день.', 0, 49, 1, "
        "'legendary', true, 1, 5, 0, 0, 0, 'default', 0, now(), now()) "
        "ON CONFLICT (slug) DO NOTHING RETURNING id"
    )).scalar()
    if pack_id is not None:
        conn.execute(sa.text(
            "INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) VALUES (:p, 'legendary', 1.0)"
        ), {"p": pack_id})

    collection_id = conn.execute(sa.text(
        "INSERT INTO equipment_collections (name, description, set_size, set_bonus_rating, set_team_chemistry, "
        "is_active, sort_order) VALUES ('Дерби', 'Для главного матча сезона.', 3, 1, 0, true, 40) RETURNING id"
    )).scalar_one()
    for i, (name, slot, icon, effect, value, coins, stars) in enumerate(DERBY):
        conn.execute(sa.text(
            "INSERT INTO equipment_items (name, description, icon, slot, rarity, collection_id, effect, effect_value, "
            "coins_price, stars_price, is_active, sort_order, sold_count, created_at, updated_at) "
            "VALUES (:name, 'Набор «Дерби». Вещь за монеты привязывается к карточке; за ⭐ — снимается.', :icon, "
            ":slot, 'epic', :col, :effect, :value, :coins, :stars, true, :sort, 0, now(), now())"
        ), {"name": name, "icon": icon, "slot": slot, "col": collection_id, "effect": effect, "value": value,
            "coins": coins, "stars": stars, "sort": 400 + i})

    for i, (name, descr, icon, rarity, target, effect, value, stars, status) in enumerate(ARTIFACTS):
        conn.execute(sa.text(
            "INSERT INTO artifacts (name, description, icon, rarity, target, effect, effect_value, link_effect_value, "
            "card_rating_bonus, coins_price, stars_price, sold_count, is_active, sort_order, status, created_at, updated_at) "
            "VALUES (:name, :descr, :icon, :rarity, :target, :effect, :value, 0, 0, 0, :stars, 0, true, :sort, :status, now(), now())"
        ), {"name": name, "descr": descr, "icon": icon, "rarity": rarity, "target": target, "effect": effect,
            "value": value, "stars": stars, "sort": 300 + i, "status": status})

    for i, (name, descr, category, emoji, coins, stars, prestige, effect, value) in enumerate(LIFESTYLE):
        conn.execute(sa.text(
            "INSERT INTO lifestyle_items (name, description, category, emoji, coins_price, stars_price, prestige, "
            "sold_count, is_active, sort_order, effect, effect_value, created_at, updated_at) "
            "VALUES (:name, :descr, :category, :emoji, :coins, :stars, :prestige, 0, true, :sort, :effect, :value, now(), now())"
        ), {"name": name, "descr": descr, "category": category, "emoji": emoji, "coins": coins, "stars": stars,
            "prestige": prestige, "sort": 300 + i, "effect": effect, "value": value})

    diamond = conn.execute(sa.text(
        "SELECT id FROM packs WHERE name IN ('Диамантовый Пак', 'Diamond Pack') AND is_active "
        "ORDER BY (name = 'Диамантовый Пак') DESC, id LIMIT 1"
    )).scalar()
    for name, descr, pack, count, coins, stars, sort in (
        ("Кофе для тренера", "Взбодрить друга перед матчем. Внутри 300 монет.", None, 1, 300, 3, 300),
        ("Букет болельщика", "За красивую победу. Внутри 1 500 монет.", None, 1, 1500, 15, 301),
        ("Сундук чемпиона", "Королевский подарок: 15 000 монет и два диамантовых пака.", diamond, 2, 15000, 150, 302),
    ):
        conn.execute(sa.text(
            "INSERT INTO gift_sets (name, description, pack_id, pack_count, coins_amount, stars_price, coins_price, "
            "kind, next_serial_number, is_active, sort_order, created_at, updated_at) "
            "VALUES (:name, :descr, :pack, :count, :coins, :stars, 0, 'bundle', 1, true, :sort, now(), now())"
        ), {"name": name, "descr": descr, "pack": pack, "count": count, "coins": coins, "stars": stars, "sort": sort})

    for i, (kind, name, style, coins, stars) in enumerate(COSMETICS):
        conn.execute(sa.text(
            "INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, "
            "is_active, sort_order, status, win_bonus_coins, created_at, updated_at) "
            "VALUES (:kind, :name, '', :style, :coins, :stars, false, true, :sort, 0, 0, now(), now())"
        ), {"kind": kind, "name": name, "style": style, "coins": coins, "stars": stars, "sort": 300 + i})


def downgrade() -> None:
    # The goods may already be bought: only the columns go (rows stay, harmless).
    op.drop_column("gift_sets", "pack_count")
    op.drop_index("ix_user_equipment_bound_card_id", table_name="user_equipment")
    op.drop_column("user_equipment", "bound_card_id")
    op.drop_column("user_equipment", "binds_on_equip")
    op.drop_column("packs", "daily_limit_per_user")
    op.drop_column("coin_packages", "bonus_pct")
