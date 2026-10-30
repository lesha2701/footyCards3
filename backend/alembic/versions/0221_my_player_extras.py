"""«Мой игрок» extras: «Спонсор» weekly contracts, gifts to friends (Stars),
numbered limited style items, new celebrations, walk-outs and trophy
showcases (my_player_extras). Celebrations: «Кулак вверх» is the one sold
for coins, every other one — «Сиу!» included — for Stars only.

Revision ID: 0221
Revises: 0220
Create Date: 2026-10-28
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0221"
down_revision: Union[str, None] = "0220"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SPONSOR_GOALS = {
    "training": {"label": "Тренировки", "target": 5, "coins": 150},
    "duel_win": {"label": "Победы в дуэлях", "target": 3, "coins": 150},
    "career_match": {"label": "Матчи в карьере", "target": 8, "coins": 150},
    "career_goal": {"label": "Голы в карьере", "target": 4, "coins": 200},
    "career_win": {"label": "Победы в карьере", "target": 4, "coins": 200},
    "game_reward": {"label": "Наградные игры", "target": 25, "coins": 150},
}
SPONSORS = [
    {"code": "volt", "name": "Volt Energy", "emoji": "⚡", "color": "#facc15",
     "goals": ["training", "game_reward", "career_match", "duel_win"]},
    {"code": "strike", "name": "Strike Boots", "emoji": "👟", "color": "#38bdf8",
     "goals": ["career_goal", "career_match", "training", "career_win"]},
    {"code": "northbay", "name": "Northbay Bank", "emoji": "🏦", "color": "#22c55e",
     "goals": ["career_win", "duel_win", "game_reward", "career_goal"]},
    {"code": "pulse", "name": "Pulse Mobile", "emoji": "📱", "color": "#a855f7",
     "goals": ["duel_win", "training", "game_reward", "career_win"]},
    {"code": "golazo", "name": "Golazo Pizza", "emoji": "🍕", "color": "#f97316",
     "goals": ["game_reward", "career_match", "duel_win", "career_goal"]},
    {"code": "tempo", "name": "Tempo Watches", "emoji": "⌚", "color": "#eab308",
     "goals": ["career_goal", "career_win", "training", "duel_win"]},
]
LIMITED = {"cel_siu_gold": 100, "walk_legend": 100}
NEW_COINS = {"cel_fist": 500, "walk_tunnel": 400, "walk_flags": 900, "sc_marble": 1500}
NEW_STARS = {
    "cel_shush": 60, "cel_flex": 60, "cel_knee": 75, "cel_calma": 90, "cel_flip": 120, "cel_siu_gold": 300,
    "walk_smoke": 60, "walk_fireworks": 100, "walk_legend": 250, "sc_gold": 75, "sc_crystal": 150,
}
# Celebrations already sold for Stars keep their price (or get this one).
STARS_CELEBRATIONS = {"cel_siu": 100, "cel_plane": 75, "cel_heart": 50, "cel_dance": 150}


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'my_player_sponsor'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'my_player_gift'")
    op.create_table(
        "my_player_sponsor_contracts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week", sa.String(8), nullable=False),
        sa.Column("brand", sa.String(32), nullable=False),
        sa.Column("goals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("progress", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("paid", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week", name="uq_my_player_sponsor_week"),
    )
    op.create_index("ix_my_player_sponsor_contracts_user_id", "my_player_sponsor_contracts", ["user_id"])
    op.create_table(
        "my_player_gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_my_player_gifts_sender_id", "my_player_gifts", ["sender_id"])
    op.create_index("ix_my_player_gifts_recipient_id", "my_player_gifts", ["recipient_id"])
    op.create_table(
        "my_player_editions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code", "number", name="uq_my_player_edition_number"),
        sa.UniqueConstraint("code", "user_id", name="uq_my_player_edition_owner"),
    )
    op.create_index("ix_my_player_editions_code", "my_player_editions", ["code"])
    op.create_index("ix_my_player_editions_user_id", "my_player_editions", ["user_id"])

    for column, value in (
        ("my_player_limited_supply", LIMITED), ("my_player_sponsor_goals", SPONSOR_GOALS),
        ("my_player_sponsors", SPONSORS), ("my_player_patron_levels", [1, 5, 20]),
    ):
        op.add_column("game_config", sa.Column(column, sa.JSON(), nullable=False, server_default=_dump(value)))
    for column, value in (
        ("my_player_sponsor_bonus_coins", "300"), ("my_player_sponsor_stars", "49"), ("my_player_sponsor_premium_pct", "200"),
    ):
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=value))

    # Prices of the new items; celebrations: coins only for «Кулак вверх».
    bind = op.get_bind()
    row = bind.execute(sa.text(
        "SELECT my_player_cosmetic_prices, my_player_cosmetic_stars_prices FROM game_config WHERE id = 1"
    )).first()
    if row is None:
        return
    coins, stars = row
    coins = json.loads(coins) if isinstance(coins, str) else dict(coins or {})
    stars = json.loads(stars) if isinstance(stars, str) else dict(stars or {})
    for code in [c for c in coins if c.startswith("cel_") and c != "cel_fist"]:
        coins.pop(code)
    stars.pop("cel_fist", None)
    for code, price in STARS_CELEBRATIONS.items():
        if not int(stars.get(code) or 0):
            stars[code] = price
    for code, price in NEW_COINS.items():
        coins.setdefault(code, price)
    for code, price in NEW_STARS.items():
        stars.setdefault(code, price)
    bind.execute(
        sa.text("UPDATE game_config SET my_player_cosmetic_prices = :coins, my_player_cosmetic_stars_prices = :stars WHERE id = 1"),
        {"coins": _dump(coins), "stars": _dump(stars)},
    )


def downgrade() -> None:
    for column in (
        "my_player_sponsor_premium_pct", "my_player_sponsor_stars", "my_player_sponsor_bonus_coins",
        "my_player_patron_levels", "my_player_sponsors", "my_player_sponsor_goals", "my_player_limited_supply",
    ):
        op.drop_column("game_config", column)
    op.drop_table("my_player_editions")
    op.drop_table("my_player_gifts")
    op.drop_table("my_player_sponsor_contracts")
