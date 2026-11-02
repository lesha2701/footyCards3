"""«Карьера игрока»: month awards besides the «Золотой мяч» and new trophy
cabinets.

- player_career_month_awards: «Золотая бутса», «Король передач», «Золотая
  перчатка», «Лучший защитник» — one row per (month, code).
- GameConfig player_career_award_coins / _prestige.
- Their trophy definitions.
- Stars prices of the new cabinets sc_stadium / sc_velvet / sc_neon (merged
  into the admin's prices, an existing price is kept).

Revision ID: 0242
Revises: 0241
Create Date: 2026-11-02
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0242"
down_revision: Union[str, None] = "0241"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TROPHIES = [
    ("player_career_golden_boot", "Золотая бутса", "Лучший бомбардир месяца в «Карьере игрока»", "👟", 66),
    ("player_career_top_assist", "Король передач", "Больше всех передач за месяц в «Карьере игрока»", "🎯", 67),
    ("player_career_golden_glove", "Золотая перчатка", "Лучший вратарь месяца в «Карьере игрока»", "🧤", 68),
    ("player_career_best_defender", "Лучший защитник", "Лучший защитник месяца в «Карьере игрока»", "🛡️", 69),
]
NEW_STARS = {"sc_stadium": 120, "sc_velvet": 150, "sc_neon": 100}


def upgrade() -> None:
    op.create_table(
        "player_career_month_awards",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("game_config", sa.Column("player_career_award_coins", sa.Integer(), nullable=False, server_default="1500"))
    op.add_column("game_config", sa.Column("player_career_award_prestige", sa.Integer(), nullable=False, server_default="25"))

    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text("SELECT code FROM trophy_definitions")).fetchall()}
    trophies = sa.table(
        "trophy_definitions",
        sa.column("code", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("icon", sa.String), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    rows = [
        {"code": c, "name": n, "description": d, "icon": i, "is_active": True, "sort_order": o}
        for c, n, d, i, o in TROPHIES if c not in existing
    ]
    if rows:
        op.bulk_insert(trophies, rows)

    row = bind.execute(sa.text("SELECT my_player_cosmetic_stars_prices FROM game_config WHERE id = 1")).fetchone()
    if row is not None:
        prices = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        prices = {**NEW_STARS, **prices}
        bind.execute(
            sa.text("UPDATE game_config SET my_player_cosmetic_stars_prices = :p WHERE id = 1"),
            {"p": json.dumps(prices, ensure_ascii=False)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT my_player_cosmetic_stars_prices FROM game_config WHERE id = 1")).fetchone()
    if row is not None:
        prices = row[0] if isinstance(row[0], dict) else json.loads(row[0] or "{}")
        for code in NEW_STARS:
            prices.pop(code, None)
        bind.execute(
            sa.text("UPDATE game_config SET my_player_cosmetic_stars_prices = :p WHERE id = 1"),
            {"p": json.dumps(prices, ensure_ascii=False)},
        )
    bind.execute(sa.text("DELETE FROM trophy_definitions WHERE code IN :codes").bindparams(
        sa.bindparam("codes", expanding=True)), {"codes": [t[0] for t in TROPHIES]})
    op.drop_column("game_config", "player_career_award_prestige")
    op.drop_column("game_config", "player_career_award_coins")
    op.drop_table("player_career_month_awards")
