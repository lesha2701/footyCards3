"""«Карьера игрока»: shared club list with «Карьера тренера», prestige
gates and salaries, contracts and the transfer window, the Champions
League, national teams, the monthly «Золотой мяч».

Revision ID: 0152
Revises: 0151
Create Date: 2026-10-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0152"
down_revision: Union[str, None] = "0151"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INT_SETTINGS = (
    ("player_career_star_salary_pct", "20"), ("player_career_prestige_salary_cap", "50"),
    ("player_career_contract_seasons", "2"), ("player_career_free_agent_level", "4"),
    ("player_career_offers_max", "3"), ("player_career_haggle_base", "90"),
    ("player_career_haggle_raise_penalty", "2"), ("player_career_haggle_repeat_penalty", "15"),
    ("player_career_cl_places", "2"), ("player_career_cl_prestige", "40"),
    ("player_career_national_prestige", "150"), ("player_career_national_win_prestige", "30"),
    ("player_career_golden_ball_min_matches", "8"), ("player_career_golden_ball_coins", "3000"),
    ("player_career_golden_ball_prestige", "50"),
)
LIST_SETTINGS = (
    ("player_career_level_ratings", "[80, 74, 68, 62, 54]"),
    ("player_career_level_salary", "[1500, 1000, 600, 350, 150]"),
    ("player_career_level_prestige", "[150, 80, 30, 10, 0]"),
    ("player_career_star_prestige", "[0, 30, 80, 160, 300]"),
    ("player_career_cl_rewards", "[300, 600, 1500]"),
    ("player_career_national_rewards", "[200, 400, 1000]"),
)
DROPPED = (
    ("player_career_rep_per_club_rating", "4"), ("player_career_salary_per_rating", "10"),
    ("player_career_min_club_cards", "5"),
)


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'player_career_event'")

    mp = "my_players"
    op.add_column(mp, sa.Column("contract_salary", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(mp, sa.Column("contract_seasons_left", sa.Integer(), nullable=False, server_default="0"))
    op.add_column(mp, sa.Column("country", sa.String(64), nullable=True))
    # Players already at a club keep it for one more season.
    op.execute("UPDATE my_players SET contract_seasons_left = 1 WHERE club_key IS NOT NULL")

    op.create_table(
        "player_career_cups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("window_key", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("coins_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "kind", "window_key", name="uq_player_career_cup_window"),
    )
    op.create_index("ix_player_career_cups_user_id", "player_career_cups", ["user_id"])
    op.create_index("ix_player_career_cups_status", "player_career_cups", ["status"])

    op.create_table(
        "player_career_month_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clean_sheets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("line", sa.String(8), nullable=False, server_default="FWD"),
        sa.UniqueConstraint("user_id", "month", name="uq_player_career_month_stat"),
    )
    op.create_index("ix_player_career_month_stats_user_id", "player_career_month_stats", ["user_id"])
    op.create_index("ix_player_career_month_stats_month", "player_career_month_stats", ["month"])

    op.create_table(
        "player_career_golden_balls",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    gc = "game_config"
    for column, default in INT_SETTINGS:
        op.add_column(gc, sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    for column, default in LIST_SETTINGS:
        op.add_column(gc, sa.Column(column, sa.JSON(), nullable=False, server_default=_json(default)))
    for column, _ in DROPPED:
        op.drop_column(gc, column)

    trophies = sa.table(
        "trophy_definitions",
        sa.column("code", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("icon", sa.String), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    existing = {r[0] for r in op.get_bind().execute(sa.text("SELECT code FROM trophy_definitions")).fetchall()}
    rows = [
        {"code": "player_career_cl_winner", "name": "Победитель Лиги чемпионов",
         "description": "Выиграл Лигу чемпионов в «Карьере игрока»", "icon": "🏆", "is_active": True, "sort_order": 63},
        {"code": "player_career_national_winner", "name": "Чемпион турнира сборных",
         "description": "Выиграл турнир сборных в «Карьере игрока»", "icon": "🌍", "is_active": True, "sort_order": 64},
        {"code": "player_career_golden_ball", "name": "Золотой мяч",
         "description": "Лучший игрок месяца в «Карьере игрока»", "icon": "⚽", "is_active": True, "sort_order": 65},
    ]
    rows = [r for r in rows if r["code"] not in existing]
    if rows:
        op.bulk_insert(trophies, rows)


def downgrade() -> None:
    gc = "game_config"
    for column, default in DROPPED:
        op.add_column(gc, sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    for column, _ in (*LIST_SETTINGS, *INT_SETTINGS):
        op.drop_column(gc, column)
    op.drop_table("player_career_golden_balls")
    op.drop_index("ix_player_career_month_stats_month", table_name="player_career_month_stats")
    op.drop_index("ix_player_career_month_stats_user_id", table_name="player_career_month_stats")
    op.drop_table("player_career_month_stats")
    op.drop_index("ix_player_career_cups_status", table_name="player_career_cups")
    op.drop_index("ix_player_career_cups_user_id", table_name="player_career_cups")
    op.drop_table("player_career_cups")
    for column in ("country", "contract_seasons_left", "contract_salary"):
        op.drop_column("my_players", column)
    # The enum value and the trophy definitions stay.
