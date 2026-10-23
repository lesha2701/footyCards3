"""seed the first «Артефакты»: legends' memorabilia

Revision ID: 0156
Revises: 0155
Create Date: 2026-10-17

Nine artifacts with small, capped bonuses (artifact_service.EFFECTS). Links
to a player / coach / stadium are looked up by name (Latin or Cyrillic) and
simply left empty when that card doesn't exist in this database — the admin
can set them later in «Абонемент, сезон, стиль» → Артефакты, and upload the
pictures there (an emoji icon is shown until then). Artifacts stay invisible
until artifacts_enabled is switched on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0156"
down_revision: Union[str, None] = "0155"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# name, icon, rarity, target, effect, value, (link kind, name patterns, linked value),
# (card bonus player name patterns, +rating), coins, stars, max_supply, description
ARTIFACTS = [
    ("Тактическая доска Фергюсона", "📋", "legendary", "club", "team_boost_pct", 1,
     ("coach", ["ferguson", "фергюсон"], 3), None, 15000, 79, None,
     "Доска, на которой рождались победы «Юнайтед». С тренером Фергюсоном команда играет ещё сильнее."),
    ("Капитанская повязка Мальдини", "🎗️", "epic", "my_player", "defense", 2,
     ("player", ["maldini", "мальдини"], 3), (["maldini", "мальдини"], 3), 9000, 49, None,
     "25 сезонов за «Милан» и капитанская повязка — надёжность в обороне."),
    ("Вратарская перчатка Яшина", "🧤", "epic", "my_player", "defense", 2,
     ("player", ["yashin", "яшин"], 3), (["yashin", "яшин"], 3), 9000, 49, None,
     "Перчатка «Чёрного паука» — единственного вратаря с «Золотым мячом»."),
    ("Бутсы Пеле", "👟", "legendary", "my_player", "shot_pp", 2,
     None, (["pele", "pelé", "пеле"], 3), 14000, 79, None,
     "Бутсы Короля футбола: удары точнее."),
    ("Кусочек газона старого Камп Ноу", "🌱", "rare", "club", "opp_home_pct", 1,
     ("stadium", ["camp nou", "камп ноу"], 2), None, 5000, 29, None,
     "Частичка легендарного поля. Дома соперник слабее — а с карточкой Камп Ноу ещё слабее."),
    ("Футболка Тотти №10", "👕", "epic", "my_player", "match_rating", 1,
     None, (["totti", "тотти"], 3), 8000, 45, None,
     "Десятка вечного капитана «Ромы»."),
    ("Мяч финала ЧМ-1998 с подписью Зидана", "⚽", "legendary", "my_player", "dribble_pp", 3,
     None, (["zidane", "зидан"], 3), 16000, 89, 1998,
     "Тот самый мяч из Сен-Дени: обыгрыш 1 на 1 легче. Тираж 1998."),
    ("Золотая бутса Месси", "🥇", "legendary", "my_player", "attack", 3,
     None, (["messi", "месси"], 3), 18000, 99, None,
     "Шесть Золотых бутс в одной — атака сильнее."),
    ("Билет на финал ЛЧ-1999", "🎟️", "rare", "club", "team_boost_pct", 1,
     ("coach", ["ferguson", "фергюсон"], 2), None, 6000, 35, 1999,
     "Барселона, 26 мая 1999: два гола в добавленное время. С тренером Фергюсоном бонус выше. Тираж 1999."),
]

_TABLES = {"player": "players", "coach": "coaches", "stadium": "stadiums"}


def _find(bind, kind: str, patterns: list[str]):
    clause = " OR ".join(f"display_name ILIKE :p{i}" for i in range(len(patterns)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(patterns)}
    return bind.execute(sa.text(f"SELECT id FROM {_TABLES[kind]} WHERE {clause} ORDER BY id LIMIT 1"), params).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    for i, (name, icon, rarity, target, effect, value, link, card, coins, stars, supply, description) in enumerate(ARTIFACTS):
        link_type = link_id = None
        link_value = 0
        if link:
            found = _find(bind, link[0], link[1])
            if found:
                link_type, link_id, link_value = link[0], found, link[2]
        card_player_id, card_bonus = None, 0
        if card:
            found = _find(bind, "player", card[0])
            if found:
                card_player_id, card_bonus = found, card[1]
        bind.execute(
            sa.text(
                """
                INSERT INTO artifacts (name, description, icon, rarity, target, effect, effect_value,
                    link_type, link_id, link_effect_value, card_player_id, card_rating_bonus,
                    coins_price, stars_price, max_supply, is_active, sort_order)
                VALUES (:name, :description, :icon, :rarity, :target, :effect, :value,
                    :link_type, :link_id, :link_value, :card_player_id, :card_bonus,
                    :coins, :stars, :supply, true, :sort)
                """
            ),
            {"name": name, "description": description, "icon": icon, "rarity": rarity, "target": target,
             "effect": effect, "value": value, "link_type": link_type, "link_id": link_id, "link_value": link_value,
             "card_player_id": card_player_id, "card_bonus": card_bonus, "coins": coins, "stars": stars,
             "supply": supply, "sort": i + 1},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for row in ARTIFACTS:
        bind.execute(
            sa.text("DELETE FROM artifacts WHERE name = :name AND sold_count = 0"), {"name": row[0]},
        )
