"""seed ten more «Артефакты»

Revision ID: 0159
Revises: 0158
Create Date: 2026-10-17

Same rules as 0156: small capped bonuses, player / coach / stadium links
resolved by name (Latin or Cyrillic) and left empty when the card is
missing; «статус» by rarity (legendary 30, epic 20, rare 10). Pictures are
uploaded in the admin panel.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0159"
down_revision: Union[str, None] = "0158"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS = {"legendary": 30, "epic": 20, "rare": 10}

# name, icon, rarity, target, effect, value, (link kind, patterns, linked value),
# (card bonus player patterns, +rating), coins, stars, max_supply, description
ARTIFACTS = [
    ("Перчатки Буффона", "🧤", "epic", "my_player", "defense", 2,
     ("player", ["buffon", "буффон"], 3), (["buffon", "буффон"], 3), 9000, 49, None,
     "28 лет в воротах: надёжность, которой нет срока годности."),
    ("Капитанская повязка Джеррарда", "🎗️", "epic", "my_player", "match_rating", 1,
     None, (["gerrard", "джеррард"], 3), 8000, 45, None,
     "Повязка капитана «Ливерпуля» — лидер поднимает игру в каждом матче."),
    ("Бутсы Роналдиньо", "👟", "legendary", "my_player", "dribble_pp", 3,
     None, (["ronaldinho", "роналдиньо"], 3), 16000, 89, None,
     "Улыбка и финты: обыгрыш 1 на 1 даётся легче."),
    ("Бутсы Криштиану Роналду", "👟", "legendary", "my_player", "shot_pp", 3,
     None, (["cristiano", "криштиану", "ronaldo cr7"], 3), 18000, 99, None,
     "Сиииии! Удары точнее, как у лучшего бомбардира в истории."),
    ("Футболка Кройфа №14", "👕", "legendary", "my_player", "skill_level", 1,
     None, (["cruyff", "кройф"], 3), 17000, 95, None,
     "Тотальный футбол: навык твоего игрока на уровень выше."),
    ("Тетрадь Гвардиолы", "📓", "legendary", "club", "team_boost_pct", 1,
     ("coach", ["guardiola", "гвардиол"], 3), None, 15000, 79, None,
     "Схемы, позиционные атаки и тики-така. С тренером Гвардиолой команда играет ещё сильнее."),
    ("Пальто Моуринью", "🧥", "epic", "club", "opp_home_pct", 1,
     ("coach", ["mourinho", "моуринью"], 2), None, 9000, 49, None,
     "«Особенный»: дома соперник играет нервно. С тренером Моуринью — ещё нервнее."),
    ("Свисток Коллины", "📣", "rare", "club", "team_boost_pct", 1,
     None, None, 5000, 29, None,
     "Свисток самого строгого арбитра: команда играет собраннее."),
    ("Шарф «You'll Never Walk Alone»", "🧣", "rare", "club", "opp_home_pct", 1,
     ("stadium", ["anfield", "энфилд"], 2), None, 5000, 29, None,
     "Гимн трибун: дома соперник слабее, а на Энфилде — ещё слабее."),
    ("Мяч «Руки Бога» 1986", "⚽", "legendary", "my_player", "attack", 3,
     None, (["maradona", "марадон"], 3), 19000, 99, 1986,
     "Мехико, 22 июня 1986. Атака сильнее. Тираж 1986."),
]

_TABLES = {"player": "players", "coach": "coaches", "stadium": "stadiums"}


def _find(bind, kind: str, patterns: list[str]):
    clause = " OR ".join(f"display_name ILIKE :p{i}" for i in range(len(patterns)))
    params = {f"p{i}": f"%{p}%" for i, p in enumerate(patterns)}
    return bind.execute(sa.text(f"SELECT id FROM {_TABLES[kind]} WHERE {clause} ORDER BY id LIMIT 1"), params).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    start = bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), 0) FROM artifacts")).scalar() or 0
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
                    coins_price, stars_price, max_supply, is_active, sort_order, status)
                VALUES (:name, :description, :icon, :rarity, :target, :effect, :value,
                    :link_type, :link_id, :link_value, :card_player_id, :card_bonus,
                    :coins, :stars, :supply, true, :sort, :status)
                """
            ),
            {"name": name, "description": description, "icon": icon, "rarity": rarity, "target": target,
             "effect": effect, "value": value, "link_type": link_type, "link_id": link_id, "link_value": link_value,
             "card_player_id": card_player_id, "card_bonus": card_bonus, "coins": coins, "stars": stars,
             "supply": supply, "sort": start + i + 1, "status": STATUS.get(rarity, 5)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for row in ARTIFACTS:
        bind.execute(sa.text("DELETE FROM artifacts WHERE name = :name AND sold_count = 0"), {"name": row[0]})
