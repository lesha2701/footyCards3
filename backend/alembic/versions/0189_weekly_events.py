"""Weekly events: «Неделя мини-игры» (a weekly leaderboard of one solo
mini-game), «Матч дня» (guess the score of a real match) and «Клубный
рейд» (a weekly boss every club beats together).

Revision ID: 0189
Revises: 0188
Create Date: 2026-10-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0189"
down_revision: Union[str, None] = "0188"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INT_COLUMNS = (
    ("weekly_cup_best_of", "5"),
    ("match_day_exact_coins", "1000"),
    ("match_day_diff_coins", "400"),
    ("match_day_outcome_coins", "200"),
    ("club_raid_hp_per_member", "3000"),
    ("club_raid_attacks_per_day", "3"),
    ("club_raid_shots", "6"),
    ("club_raid_damage_per_goal", "100"),
    ("club_raid_reward_coins", "1000"),
    ("club_raid_reward_budget", "2000"),
)
FLAGS = ("weekly_cup_enabled", "match_day_enabled", "club_raid_enabled")


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'weekly_cup_result'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'match_day_result'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'weekly_cup_prize'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'match_day_reward'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'raid_reward'")

    op.create_table(
        "weekly_cup_weeks",
        sa.Column("week_start", sa.Date(), primary_key=True),
        sa.Column("game", sa.String(24), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "weekly_cup_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("games", sa.Integer(), nullable=False),
        sa.Column("prize_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("week_start", "user_id", name="uq_weekly_cup_result"),
    )
    op.create_table(
        "match_day_fixtures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("home", sa.String(64), nullable=False),
        sa.Column("away", sa.String(64), nullable=False),
        sa.Column("league", sa.String(64), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("home_score", sa.Integer(), nullable=True),
        sa.Column("away_score", sa.Integer(), nullable=True),
        sa.Column("result_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "match_day_predictions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fixture_id", sa.Integer(), sa.ForeignKey("match_day_fixtures.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("home", sa.Integer(), nullable=False),
        sa.Column("away", sa.Integer(), nullable=False),
        sa.Column("reward_coins", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fixture_id", "user_id", name="uq_match_day_prediction"),
    )
    op.create_table(
        "club_raids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("boss", sa.String(24), nullable=False),
        sa.Column("hp", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defeated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("club_id", "week_start", name="uq_club_raid_week"),
    )
    op.create_table(
        "club_raid_attacks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raid_id", sa.Integer(), sa.ForeignKey("club_raids.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("shots", sa.Integer(), nullable=False),
        sa.Column("goals", sa.Integer(), nullable=False),
        sa.Column("damage", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_raid_attacks_user_day", "club_raid_attacks", ["user_id", "day"])

    for name in FLAGS:
        op.add_column("game_config", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("club_raid_reward_pack_id", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column(
        "weekly_cup_games", sa.JSON(), nullable=False,
        server_default=sa.text("'[\"penalty\", \"free_kick\", \"memory\", \"saboteur\", \"pairs\"]'::json"),
    ))
    op.add_column("game_config", sa.Column(
        "weekly_cup_prizes", sa.JSON(), nullable=False,
        server_default=sa.text("'[5000, 3000, 2000, 1000, 1000, 500, 500, 500, 500, 500]'::json"),
    ))


def downgrade() -> None:
    for name in ("weekly_cup_prizes", "weekly_cup_games", "club_raid_reward_pack_id", *[n for n, _ in INT_COLUMNS], *FLAGS):
        op.drop_column("game_config", name)
    op.drop_index("ix_club_raid_attacks_user_day", table_name="club_raid_attacks")
    for table in ("club_raid_attacks", "club_raids", "match_day_predictions", "match_day_fixtures",
                  "weekly_cup_results", "weekly_cup_weeks"):
        op.drop_table(table)
