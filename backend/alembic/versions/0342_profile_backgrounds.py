"""Profile header backgrounds become pictures (frontend assets/profile/bg/<style_key>.webp):
the old gradients keep their rows, and three new backgrounds are added —
«Золотая лихорадка» (its gradient existed but was never sold) and the
premium «Легенда» / «Неоновый город»; «Северное сияние» drops to 75 coins. Prices are ordinary `cosmetics` rows,
edited in the admin panel.

Revision ID: 0342
Revises: 0341
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0342"
down_revision: Union[str, None] = "0341"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (name, description, style_key, coins, stars, order)
BACKGROUNDS = (
    ("Золотая лихорадка", "Фон профиля: золото и кубок в сокровищнице", "gold_rush", 6000, 45, 4),
    ("Легенда", "Фон профиля: золотой тоннель на поле", "legend", 0, 99, 7),
    ("Неоновый город", "Фон профиля: клетка на крыше над неоновым городом", "neon_city", 0, 129, 8),
)


def upgrade() -> None:
    conn = op.get_bind()
    for name, description, key, coins, stars, order in BACKGROUNDS:
        exists = conn.execute(sa.text(
            "SELECT 1 FROM cosmetics WHERE kind = 'profile_background' AND style_key = :key"
        ), {"key": key}).first()
        if exists:
            continue
        conn.execute(sa.text(
            "INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, sort_order) "
            "VALUES ('profile_background', :name, :description, :key, :coins, :stars, false, :order)"
        ), {"name": name, "description": description, "key": key, "coins": coins, "stars": stars, "order": order})
    op.execute("UPDATE cosmetics SET coins_price = 75 WHERE kind = 'profile_background' AND style_key = 'aurora'")


def downgrade() -> None:
    op.execute("UPDATE cosmetics SET coins_price = 8000 WHERE kind = 'profile_background' AND style_key = 'aurora'")
    keys = ", ".join(f"'{k}'" for _, _, k, _, _, _ in BACKGROUNDS)
    op.execute(
        "DELETE FROM user_cosmetics WHERE cosmetic_id IN "
        f"(SELECT id FROM cosmetics WHERE kind = 'profile_background' AND style_key IN ({keys}))"
    )
    op.execute(f"DELETE FROM cosmetics WHERE kind = 'profile_background' AND style_key IN ({keys})")
