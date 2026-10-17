"""seed «This is Anfield» plaque and Maradona's shirt

Revision ID: 0160
Revises: 0159
Create Date: 2026-10-17

Same rules as 0156/0159: small capped bonuses, player / coach / stadium links
resolved by name (Latin or Cyrillic) and left empty when the card is
missing; «статус» by rarity (legendary 30, epic 20, rare 10). Pictures are
uploaded in the admin panel.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0160"
down_revision: Union[str, None] = "0159"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS = {"legendary": 30, "epic": 20, "rare": 10}

# name, icon, rarity, target, effect, value, (link kind, patterns, linked value),
# (card bonus player patterns, +rating), coins, stars, max_supply, description
ARTIFACTS = [
    ("Табличка This is Anfield", "🪧", "epic", "club", "opp_home_pct", 1,
     ("stadium", ["anfield", "энфилд"], 2), None, 9000, 49, None,
     "Табличка над выходом на поле: дома соперник слабее, а на Энфилде — ещё слабее."),
    ("Футболка Марадоны", "👕", "legendary", "my_player", "dribble_pp", 2,
     ("player", ["maradona", "марадон"], 3), (["maradona", "марадон"], 3), 18000, 99, None,
     "Десятка «Пибе де Оро»: обыгрыш 1 на 1 легче, а с карточкой Марадоны — ещё легче."),
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
