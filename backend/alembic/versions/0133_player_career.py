""""Карьера игрока": seasons of «Мой игрок» at clubs built from real cards,
club / reputation / career stats on my_players, settings, notification and
transaction types.

Revision ID: 0133
Revises: 0132
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0133"
down_revision: Union[str, None] = "0132"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'player_career_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_career_round_result'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_career_season_finished'")
    op.create_table(
        "player_career_seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_key", sa.String(96), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("final_place", sa.Integer(), nullable=True),
        sa.Column("coins_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_player_career_seasons_user_id", "player_career_seasons", ["user_id"])
    op.create_index("ix_player_career_seasons_status", "player_career_seasons", ["status"])
    op.add_column("my_players", sa.Column("club_key", sa.String(96), nullable=True))
    op.add_column("my_players", sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("my_players", sa.Column("career_stats", sa.JSON(), nullable=False, server_default=_json("{}")))

    gc = "game_config"
    op.add_column(gc, sa.Column("player_career_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in (
        ("player_career_min_club_cards", "5"), ("player_career_rating_margin", "5"),
        ("player_career_rep_per_club_rating", "4"), ("player_career_rep_per_goal", "3"),
        ("player_career_rep_per_assist", "2"), ("player_career_rep_per_win", "2"),
        ("player_career_rep_title", "30"), ("player_career_match_reward_win", "25"),
        ("player_career_match_reward_draw", "10"), ("player_career_goal_reward", "10"),
        ("player_career_match_xp", "15"),
    ):
        op.add_column(gc, sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column(gc, sa.Column(
        "player_career_place_rewards", sa.JSON(), nullable=False,
        server_default=_json("[1000, 700, 500, 350, 250, 180, 120, 80]"),
    ))

    trophies = sa.table(
        "trophy_definitions",
        sa.column("code", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("icon", sa.String), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(sa.text("SELECT code FROM trophy_definitions")).fetchall()}
    rows = [
        {"code": "player_career_champion", "name": "Чемпион лиги", "description": "Выиграл лигу в «Карьере игрока»",
         "icon": "🏆", "is_active": True, "sort_order": 60},
        {"code": "player_career_top_scorer", "name": "Лучший бомбардир", "description": "Лучший бомбардир сезона в «Карьере игрока»",
         "icon": "👟", "is_active": True, "sort_order": 61},
        {"code": "player_career_mvp", "name": "Игрок сезона", "description": "Средняя оценка сезона 7.5+ в «Карьере игрока»",
         "icon": "⭐", "is_active": True, "sort_order": 62},
    ]
    rows = [r for r in rows if r["code"] not in existing]
    if rows:
        op.bulk_insert(trophies, rows)


def downgrade() -> None:
    gc = "game_config"
    op.drop_column(gc, "player_career_place_rewards")
    for name in (
        "player_career_match_xp", "player_career_goal_reward", "player_career_match_reward_draw",
        "player_career_match_reward_win", "player_career_rep_title", "player_career_rep_per_win",
        "player_career_rep_per_assist", "player_career_rep_per_goal", "player_career_rep_per_club_rating",
        "player_career_rating_margin", "player_career_min_club_cards", "player_career_enabled",
    ):
        op.drop_column(gc, name)
    for column in ("career_stats", "reputation", "club_key"):
        op.drop_column("my_players", column)
    op.drop_index("ix_player_career_seasons_status", table_name="player_career_seasons")
    op.drop_index("ix_player_career_seasons_user_id", table_name="player_career_seasons")
    op.drop_table("player_career_seasons")
    # Enum values and trophy definitions stay (enum values can't be dropped;
    # trophies may already be awarded).
