"""«Карьера тренера» tactics and divisions: familiarity + match plan on
participants, counter/familiarity/plan/adaptive-bot settings on GameConfig;
season/participant division with promotion and relegation.

Seasons started before this revision have no state["tactics_version"] and
keep playing the original match path (career_service._play_round).

Revision ID: 0138
Revises: 0135
Create Date: 2026-10-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0138"
# 0136/0137 are taken by parallel branches (blackjack, card/club chemistry);
# whichever merges later re-points its down_revision to the current head.
down_revision: Union[str, None] = "0135"
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
)
CONFIG_JSON_COLUMNS = (
    ("career_tactics_tuning", "{}"),
    ("career_bot_counter_chance_pct", "[0, 60, 85]"),
    ("career_division_rating_offset", "[6, 3, 0, -3, -6]"),
    ("career_division_reward_pct", "[250, 200, 150, 125, 100]"),
    ("career_division_bot_level", '["legend", "legend", "pro", "pro", "amateur"]'),
)


def upgrade() -> None:
    op.add_column("career_participants", sa.Column("familiarity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("career_participants", sa.Column("familiar_formation", sa.String(16), nullable=True))
    op.add_column("career_participants", sa.Column("familiar_tactic", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("tactic", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("match_plan", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("division", sa.Integer(), nullable=True))
    op.add_column("career_participants", sa.Column("next_division", sa.Integer(), nullable=True))
    op.add_column("career_seasons", sa.Column("division", sa.Integer(), nullable=True))
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, default in CONFIG_JSON_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.JSON(), nullable=False, server_default=sa.text(f"'{default}'::json")))


def downgrade() -> None:
    for name, _ in reversed(CONFIG_JSON_COLUMNS):
        op.drop_column("game_config", name)
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
    op.drop_column("career_seasons", "division")
    for column in ("next_division", "division", "match_plan", "tactic", "familiar_tactic", "familiar_formation", "familiarity"):
        op.drop_column("career_participants", column)
