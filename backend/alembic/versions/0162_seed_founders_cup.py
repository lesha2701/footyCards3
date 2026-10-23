"""seed «Золотой кубок основателей VICTOR FC»; new artifacts start inactive

Revision ID: 0162
Revises: 0161
Create Date: 2026-10-17

100 numbered copies, never sold in the shop (is_active = false, no prices):
the admin hands it out to the top donors (Абонемент, сезон, стиль →
Артефакты → «Подарить топ-донатерам»). +2% team strength in «Карьера
тренера» and +100 «статус».

The twelve artifacts added in 0159/0160 are switched off (not in the shop)
until the admin turns each one on — unless someone already owns a copy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0162"
down_revision: Union[str, None] = "0161"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Золотой кубок основателей VICTOR FC"
NEW_ARTIFACTS = [
    "Перчатки Буффона", "Капитанская повязка Джеррарда", "Бутсы Роналдиньо", "Бутсы Криштиану Роналду",
    "Футболка Кройфа №14", "Тетрадь Гвардиолы", "Пальто Моуринью", "Свисток Коллины",
    "Шарф «You'll Never Walk Alone»", "Мяч «Руки Бога» 1986", "Табличка This is Anfield", "Футболка Марадоны",
]


def upgrade() -> None:
    bind = op.get_bind()
    start = bind.execute(sa.text("SELECT COALESCE(MAX(sort_order), 0) FROM artifacts")).scalar() or 0
    bind.execute(
        sa.text(
            """
            INSERT INTO artifacts (name, description, icon, rarity, target, effect, effect_value,
                link_effect_value, card_rating_bonus, coins_price, stars_price, max_supply,
                is_active, sort_order, status)
            VALUES (:name, :description, '🏆', 'diamond', 'club', 'team_boost_pct', 2,
                0, 0, 0, 0, 100, false, :sort, 100)
            """
        ),
        {
            "name": NAME, "sort": start + 1,
            "description": "Всего 100 номерных экземпляров — только в подарок лучшим болельщикам игры. "
                           "Не продаётся. Команда играет сильнее.",
        },
    )
    bind.execute(
        sa.text("UPDATE artifacts SET is_active = false WHERE name = ANY(:names) AND sold_count = 0"),
        {"names": NEW_ARTIFACTS},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE artifacts SET is_active = true WHERE name = ANY(:names)"), {"names": NEW_ARTIFACTS},
    )
    op.get_bind().execute(sa.text("DELETE FROM artifacts WHERE name = :name AND sold_count = 0"), {"name": NAME})
