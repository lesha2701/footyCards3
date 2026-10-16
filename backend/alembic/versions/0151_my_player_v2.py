"""«Мой игрок» v2: level-up screen, training streak, freshness, friend duels,
line change, Stars cosmetics, «Имущество» effects, career salary and
objectives.

Revision ID: 0151
Revises: 0150
Create Date: 2026-10-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0151"
down_revision: Union[str, None] = "0150"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Starter «Имущество» items (seeded by 0132) get a useful effect; the admin can change it.
STARTER_EFFECTS = [
    ("Хэтчбек", "freshness_regen", 1),
    ("Спорткар", "freshness_regen", 2),
    ("Квартира у стадиона", "xp_bonus_pct", 3),
    ("Вилла у моря", "xp_bonus_pct", 5),
    ("Пакет акций клуба", "weekly_income", 300),
    ("Личный самолёт", "xp_bonus_pct", 10),
]


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'my_player_duel_reward'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'my_player_role_change'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'lifestyle_income'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'my_player_duel'")

    mp = "my_players"
    op.add_column(mp, sa.Column("training_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(mp, sa.Column("level_seen", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(mp, sa.Column("freshness", sa.Integer(), nullable=False, server_default="100"))
    op.add_column(mp, sa.Column("freshness_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(mp, sa.Column("duels_day", sa.Date(), nullable=True))
    op.add_column(mp, sa.Column("duels_today", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "my_player_duels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("my_goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opp_goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.String(8), nullable=False),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events", sa.JSON(), nullable=False, server_default=_json("[]")),
        sa.Column("snapshot", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_my_player_duels_user_created", "my_player_duels", ["user_id", "created_at"])
    op.create_index("ix_my_player_duels_opponent_user_id", "my_player_duels", ["opponent_user_id"])

    op.add_column("lifestyle_items", sa.Column("effect", sa.String(24), nullable=False, server_default="none"))
    op.add_column("lifestyle_items", sa.Column("effect_value", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_lifestyle_items", sa.Column("income_claimed_at", sa.DateTime(timezone=True), nullable=True))
    items = sa.table(
        "lifestyle_items", sa.column("name", sa.String), sa.column("effect", sa.String), sa.column("effect_value", sa.Integer),
    )
    for name, effect, value in STARTER_EFFECTS:
        op.execute(items.update().where(items.c.name == name).values(effect=effect, effect_value=value))

    gc = "game_config"
    for column, default in (
        ("my_player_streak_days", "7"), ("my_player_streak_tokens", "1"),
        ("my_player_freshness_per_match", "15"), ("my_player_freshness_regen_per_hour", "1"),
        ("my_player_freshness_training", "20"), ("my_player_fatigue_max_penalty", "5"),
        ("my_player_duels_per_day", "5"), ("my_player_duel_reward_win", "30"),
        ("my_player_duel_reward_draw", "10"), ("my_player_duel_xp", "10"),
        ("my_player_role_change_coins", "25000"), ("my_player_role_change_stars", "300"),
        ("player_career_salary_per_rating", "10"), ("player_career_objective_coins", "150"),
        ("player_career_objective_rep", "5"),
    ):
        op.add_column(gc, sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    op.add_column(gc, sa.Column(
        "my_player_cosmetic_stars_prices", sa.JSON(), nullable=False,
        server_default=_json(
            '{"crown": 150, "bg_galaxy": 75, "bg_champions": 100, "fx_sparkle": 50, "fx_fire": 75, "fx_lightning": 100}'
        ),
    ))
    # New coin cosmetics; prices the admin already set are kept (right side wins).
    op.execute(
        "UPDATE game_config SET my_player_cosmetic_prices = "
        "('{\"captain\": 700, \"headphones\": 900, \"bg_night\": 900}'::jsonb || my_player_cosmetic_prices::jsonb)::json"
    )


def downgrade() -> None:
    gc = "game_config"
    for column in (
        "my_player_cosmetic_stars_prices",
        "player_career_objective_rep", "player_career_objective_coins", "player_career_salary_per_rating",
        "my_player_role_change_stars", "my_player_role_change_coins",
        "my_player_duel_xp", "my_player_duel_reward_draw", "my_player_duel_reward_win", "my_player_duels_per_day",
        "my_player_fatigue_max_penalty", "my_player_freshness_training",
        "my_player_freshness_regen_per_hour", "my_player_freshness_per_match",
        "my_player_streak_tokens", "my_player_streak_days",
    ):
        op.drop_column(gc, column)
    op.drop_column("user_lifestyle_items", "income_claimed_at")
    op.drop_column("lifestyle_items", "effect_value")
    op.drop_column("lifestyle_items", "effect")
    op.drop_index("ix_my_player_duels_opponent_user_id", table_name="my_player_duels")
    op.drop_index("ix_my_player_duels_user_created", table_name="my_player_duels")
    op.drop_table("my_player_duels")
    for column in ("duels_today", "duels_day", "freshness_at", "freshness", "level_seen", "training_streak"):
        op.drop_column("my_players", column)
    # The enum values stay: Postgres can't drop enum values.
