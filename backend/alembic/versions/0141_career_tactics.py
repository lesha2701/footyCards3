"""«Карьера тренера» tactics and divisions: familiarity + match plan on
participants, counter/familiarity/plan/adaptive-bot settings on GameConfig;
season/participant division with promotion and relegation.

Seasons started before this revision have no state["tactics_version"] and
keep playing the original match path (career_service._play_round).

Revision ID: 0141
Revises: 0140
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0141"
down_revision: Union[str, None] = "0140"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("career_familiarity_axis_keep_pct", "80"),
    ("career_squad_size", "22"),
    ("career_familiarity_step_tenths", "20"),
    ("career_familiarity_max_tenths", "90"),
    ("career_familiarity_keep_pct", "50"),
    ("career_max_plan_rules", "3"),
    ("career_max_substitutions", "3"),
    ("career_division_count", "5"),
    ("career_division_promote", "2"),
    ("career_division_relegate", "2"),
    ("career_rep_title", "25"),
    ("career_rep_promotion", "10"),
    ("career_rep_relegation", "-10"),
    ("career_rep_cup", "15"),
    ("career_inactive_days", "3"),
    ("career_core_min", "15"),
    ("career_core_keep_pct", "50"),
    ("career_camp_physical_pct", "30"),
    ("career_camp_physical_rounds", "3"),
    ("career_camp_tactical_tenths", "40"),
    ("career_tenure_minutes_per_point", "900"),
    ("career_tenure_max", "2"),
    ("career_division_club_count", "10"),
)
CONFIG_JSON_COLUMNS = (
    ("career_tactics_tuning", "{}"),
    ("career_bot_counter_chance_pct", "[0, 60, 85]"),
    ("career_division_rating_offset", "[6, 3, 0, -3, -6]"),
    ("career_division_reward_pct", "[250, 200, 150, 125, 100]"),
    ("career_division_bot_level", '["legend", "legend", "pro", "pro", "amateur"]'),
    ("career_ambition_bonus_pct", "[10, 25, 50]"),
    ("career_ambition_rep_success", "[5, 10, 20]"),
    ("career_ambition_rep_fail", "[-3, -6, -15]"),
    ("career_rep_levels", "[0, 40, 120, 250, 500]"),
    ("career_cup_rewards", "[800, 400, 200]"),
)


def upgrade() -> None:
    op.add_column("career_participants", sa.Column("familiarity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("career_participants", sa.Column("familiar_formation", sa.String(16), nullable=True))
    op.add_column("career_participants", sa.Column("familiar_tactic", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("tactic", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("match_plan", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("set_pieces", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("ambition", sa.String(16), nullable=True))
    op.add_column("career_participants", sa.Column("training", sa.String(16), nullable=True))
    op.create_table(
        "career_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("division", sa.Integer(), nullable=False),
        sa.Column("reputation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seasons_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("titles", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("promotions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("objectives_met", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenure", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("league", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("career_participants", sa.Column("division", sa.Integer(), nullable=True))
    op.add_column("career_participants", sa.Column("next_division", sa.Integer(), nullable=True))
    op.add_column("career_seasons", sa.Column("division", sa.Integer(), nullable=True))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, default in CONFIG_JSON_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'::json")))
    op.add_column("game_config", sa.Column("career_cup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("career_offseason_auto", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("career_participants", sa.Column("camp", sa.String(16), nullable=True))
    op.add_column("career_participants", sa.Column("core_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("career_participants", sa.Column("carried_familiarity", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "career_clubs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("division", sa.Integer(), nullable=False, index=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="generated"),
        sa.Column("pool_club", sa.String(128), nullable=True),
        sa.Column("rating_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("formation", sa.String(16), nullable=True),
        sa.Column("preset", sa.String(16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("career_clubs")
    for column in ("carried_familiarity", "core_count", "camp"):
        op.drop_column("career_participants", column)
    op.drop_column("game_config", "career_offseason_auto")
    op.drop_column("game_config", "career_cup_enabled")
    for name, _ in reversed(CONFIG_JSON_COLUMNS):
        op.drop_column("game_config", name)
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_table("career_profiles")
    op.drop_column("career_seasons", "division")
    for column in ("training", "ambition", "next_division", "division", "set_pieces", "match_plan", "tactic", "familiar_tactic", "familiar_formation", "familiarity"):
        op.drop_column("career_participants", column)
