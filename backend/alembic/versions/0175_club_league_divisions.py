"""«Лига клубов» divisions (Бронза → Серебро → Золото), seasons with
promotion and relegation, and the season results the trophy room shows.

Revision ID: 0175
Revises: 0174
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0175"
down_revision: Union[str, None] = "0174"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("club_league_season_weeks", "4"),
    ("club_league_promote_count", "3"),
    ("club_league_relegate_count", "3"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_league_promoted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_league_relegated'")
    op.add_column("clubs", sa.Column("league_division", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("club_league_results", sa.Column("division", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "club_season_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_end_week", sa.Date(), nullable=False),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("division", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("moved", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("season_end_week", "club_id", name="uq_club_season_result_once"),
    )
    op.create_index("ix_club_season_results_club_id", "club_season_results", ["club_id"])
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column(
        "club_league_division_reward_pct", sa.JSON(), nullable=False,
        server_default=sa.text("'[100, 150, 200]'::json"),
    ))


def downgrade() -> None:
    op.drop_column("game_config", "club_league_division_reward_pct")
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
    op.drop_index("ix_club_season_results_club_id", table_name="club_season_results")
    op.drop_table("club_season_results")
    op.drop_column("club_league_results", "division")
    op.drop_column("clubs", "league_division")
    # Enum values stay: Postgres can't drop enum values.
