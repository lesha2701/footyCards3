"""«Карьера игрока» v3: key moments, roles and the coach's trust, injuries,
story events, the friends' league, weekly rankings and tasks, club Halls of
Fame, «Карьера Pro», agents, fast seasons, the daily chest.

Revision ID: 0166
Revises: 0165
Create Date: 2026-10-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0166"
down_revision: Union[str, None] = "0165"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INT_SETTINGS = (
    ("player_career_moments", "2"),
    ("player_career_moment_hit_pct", "18"),
    ("player_career_moment_window_hours", "6"),
    ("player_career_bench_gap", "3"),
    ("player_career_bench_play_pct", "40"),
    ("player_career_trust_starter", "70"),
    ("player_career_trust_captain", "85"),
    ("player_career_captain_salary_pct", "10"),
    ("player_career_injury_freshness", "40"),
    ("player_career_injury_max_pct", "20"),
    ("player_career_heal_coins", "500"),
    ("player_career_heal_stars", "20"),
    ("player_career_refresh_coins", "300"),
    ("player_career_refresh_stars", "15"),
    ("player_career_event_every", "3"),
    ("player_career_event_coins", "100"),
    ("player_career_event_prestige", "5"),
    ("player_career_derby_multiplier", "2"),
    ("player_career_pro_stars", "299"),
    ("player_career_pro_days", "30"),
    ("player_career_pro_xp_pct", "50"),
    ("player_career_agent_stars", "50"),
    ("player_career_agent_haggle_bonus", "15"),
    ("player_career_save_offer_stars", "30"),
    ("player_career_fast_season_stars", "100"),
    ("player_career_fast_round_minutes", "120"),
    ("player_career_chest_coins_min", "50"),
    ("player_career_chest_coins_max", "200"),
    ("player_career_chest_token_pct", "10"),
    ("player_career_weekly_goals", "5"),
    ("player_career_weekly_matches", "10"),
    ("player_career_weekly_rating_x10", "70"),
)
LIST_SETTINGS = (
    ("player_career_weekly_coins", "[300, 200, 400]"),
    ("player_career_friends_rewards", "[800, 500, 300]"),
)
MP_COLUMNS = (
    ("trust", sa.Integer(), "50"), ("injury_rounds", sa.Integer(), "0"),
    ("agent_credits", sa.Integer(), "0"), ("fast_season_credits", sa.Integer(), "0"),
)
NEW_STARS_PRICES = (
    '{"bg_goal": 75, "bg_national": 75, "cel_siu": 100, "cel_plane": 75, "cel_heart": 50, "cel_dance": 150}'
)


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    for name, type_, default in MP_COLUMNS:
        op.add_column("my_players", sa.Column(name, type_, nullable=False, server_default=default))
    op.add_column("my_players", sa.Column("pro_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("my_players", sa.Column("pro_bonus_day", sa.Date(), nullable=True))
    op.add_column("my_players", sa.Column("chest_day", sa.Date(), nullable=True))

    op.create_table(
        "player_career_week_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week", sa.String(8), nullable=False),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clean_sheets", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.Float(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "week", name="uq_player_career_week_stat"),
    )
    op.create_index("ix_player_career_week_stats_user_id", "player_career_week_stats", ["user_id"])
    op.create_index("ix_player_career_week_stats_week", "player_career_week_stats", ["week"])

    op.create_table(
        "player_career_weekly_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week", sa.String(8), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "week", "code", name="uq_player_career_weekly_claim"),
    )
    op.create_index("ix_player_career_weekly_claims_user_id", "player_career_weekly_claims", ["user_id"])

    op.create_table(
        "player_career_club_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_key", sa.String(96), nullable=False),
        sa.Column("club_name", sa.String(64), nullable=False),
        sa.Column("seasons", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("titles", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "club_key", name="uq_player_career_club_record"),
    )
    op.create_index("ix_player_career_club_records_user_id", "player_career_club_records", ["user_id"])
    op.create_index("ix_player_career_club_records_club_key", "player_career_club_records", ["club_key"])

    op.create_table(
        "player_career_friend_leagues",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="lobby"),
        sa.Column("rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_player_career_friend_leagues_owner_id", "player_career_friend_leagues", ["owner_id"])
    op.create_index("ix_player_career_friend_leagues_status", "player_career_friend_leagues", ["status"])
    op.create_table(
        "player_career_friend_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("league_id", sa.Integer(), sa.ForeignKey("player_career_friend_leagues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="invited"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("league_id", "user_id", name="uq_player_career_friend_member"),
    )
    op.create_index("ix_player_career_friend_members_league_id", "player_career_friend_members", ["league_id"])
    op.create_index("ix_player_career_friend_members_user_id", "player_career_friend_members", ["user_id"])

    gc = "game_config"
    # Fast seasons stay off until the admin switches them on.
    op.add_column(gc, sa.Column("player_career_fast_season_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    for column, default in INT_SETTINGS:
        op.add_column(gc, sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    for column, default in LIST_SETTINGS:
        op.add_column(gc, sa.Column(column, sa.JSON(), nullable=False, server_default=_json(default)))
    # New Stars cosmetics; prices the admin already set are kept (right side wins).
    op.execute(
        "UPDATE game_config SET my_player_cosmetic_stars_prices = "
        f"('{NEW_STARS_PRICES}'::jsonb || my_player_cosmetic_stars_prices::jsonb)::json"
    )

    trophies = sa.table(
        "trophy_definitions",
        sa.column("code", sa.String), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("icon", sa.String), sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    existing = {r[0] for r in op.get_bind().execute(sa.text("SELECT code FROM trophy_definitions")).fetchall()}
    if "player_career_friends_champion" not in existing:
        op.bulk_insert(trophies, [{
            "code": "player_career_friends_champion", "name": "Чемпион лиги друзей",
            "description": "Выиграл лигу друзей в «Карьере игрока»", "icon": "🤝", "is_active": True, "sort_order": 66,
        }])


def downgrade() -> None:
    gc = "game_config"
    for column, _ in (*LIST_SETTINGS, *INT_SETTINGS):
        op.drop_column(gc, column)
    op.drop_column(gc, "player_career_fast_season_enabled")
    op.drop_index("ix_player_career_friend_members_user_id", table_name="player_career_friend_members")
    op.drop_index("ix_player_career_friend_members_league_id", table_name="player_career_friend_members")
    op.drop_table("player_career_friend_members")
    op.drop_index("ix_player_career_friend_leagues_status", table_name="player_career_friend_leagues")
    op.drop_index("ix_player_career_friend_leagues_owner_id", table_name="player_career_friend_leagues")
    op.drop_table("player_career_friend_leagues")
    op.drop_index("ix_player_career_club_records_club_key", table_name="player_career_club_records")
    op.drop_index("ix_player_career_club_records_user_id", table_name="player_career_club_records")
    op.drop_table("player_career_club_records")
    op.drop_index("ix_player_career_weekly_claims_user_id", table_name="player_career_weekly_claims")
    op.drop_table("player_career_weekly_claims")
    op.drop_index("ix_player_career_week_stats_week", table_name="player_career_week_stats")
    op.drop_index("ix_player_career_week_stats_user_id", table_name="player_career_week_stats")
    op.drop_table("player_career_week_stats")
    for column in ("chest_day", "pro_bonus_day", "pro_until", "fast_season_credits", "agent_credits", "injury_rounds", "trust"):
        op.drop_column("my_players", column)
    # The trophy definition and the cosmetic prices stay.
