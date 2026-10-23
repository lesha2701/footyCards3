"""«Экипировка»: the seeded things cost more (closer to «Артефакты»).

Only a thing still at its seeded price is changed — a price an admin has
already set by hand stays as it is. Downgrade puts the old seeded prices back
the same way.

Revision ID: 0184
Revises: 0183
Create Date: 2026-10-20

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0184"
down_revision: Union[str, None] = "0183"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# name: ((old coins, old stars), (new coins, new stars))
PRICES = {
    "Бутсы «Ретро-70»": ((300, 0), (1500, 0)),
    "Форма «Ретро-70»": ((400, 0), (2000, 0)),
    "Гетры «Ретро-70»": ((300, 0), (1500, 0)),
    "Бутсы «Неон»": ((900, 40), (4000, 80)),
    "Гетры «Неон»": ((900, 40), (4000, 80)),
    "Браслет «Неон»": ((1200, 50), (5000, 100)),
    "Перчатки «Стена»": ((500, 0), (2500, 0)),
    "Капитанская повязка": ((2000, 100), (9000, 180)),
    "Счастливая монета": ((2500, 0), (10000, 0)),
    "Мяч финала": ((0, 150), (0, 300)),
}

_items = sa.table(
    "equipment_items",
    sa.column("name", sa.String),
    sa.column("coins_price", sa.Integer),
    sa.column("stars_price", sa.Integer),
)


def _move(frm: int, to: int) -> None:
    for name, prices in PRICES.items():
        (from_coins, from_stars), (to_coins, to_stars) = prices[frm], prices[to]
        op.execute(
            _items.update()
            .where(_items.c.name == name, _items.c.coins_price == from_coins, _items.c.stars_price == from_stars)
            .values(coins_price=to_coins, stars_price=to_stars)
        )


def upgrade() -> None:
    _move(0, 1)


def downgrade() -> None:
    _move(1, 0)
