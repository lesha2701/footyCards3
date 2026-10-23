"""«Клубные войны»: weekly 48-hour club-vs-club by members' activity,
paired by an Elo war rating.

Revision ID: 0176
Revises: 0175
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0176"
down_revision: Union[str, None] = "0175"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_war_started'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_war_finished'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'war_reward'")
    op.add_column("clubs", sa.Column("war_rating", sa.Integer(), nullable=False, server_default="1000"))
    op.create_table(
        "club_war_rounds",
        sa.Column("week_start", sa.Date(), primary_key=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_wars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_start", sa.Date(), sa.ForeignKey("club_war_rounds.week_start", ondelete="CASCADE"), nullable=False),
        sa.Column("club_a_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("club_b_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("score_a", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_b", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("winner_club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("week_start", "club_a_id", name="uq_club_war_week_club_a"),
        sa.UniqueConstraint("week_start", "club_b_id", name="uq_club_war_week_club_b"),
    )
    op.create_index("ix_club_wars_status_ends_at", "club_wars", ["status", "ends_at"])
    op.add_column("game_config", sa.Column("club_war_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("club_war_start_weekday", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("game_config", sa.Column("club_war_start_hour", sa.Integer(), nullable=False, server_default="18"))
    op.add_column("game_config", sa.Column("club_war_duration_hours", sa.Integer(), nullable=False, server_default="48"))
    op.add_column("game_config", sa.Column("club_war_min_members", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("club_war_member_cap", sa.Integer(), nullable=False, server_default="100"))
    op.add_column("game_config", sa.Column("club_war_win_budget", sa.Integer(), nullable=False, server_default="3000"))
    op.add_column("game_config", sa.Column("club_war_draw_budget", sa.Integer(), nullable=False, server_default="1500"))
    op.add_column("game_config", sa.Column("club_war_loss_budget", sa.Integer(), nullable=False, server_default="500"))
    op.add_column("game_config", sa.Column("club_war_win_member_coins", sa.Integer(), nullable=False, server_default="200"))


def downgrade() -> None:
    op.drop_column("game_config", "club_war_win_member_coins")
    op.drop_column("game_config", "club_war_loss_budget")
    op.drop_column("game_config", "club_war_draw_budget")
    op.drop_column("game_config", "club_war_win_budget")
    op.drop_column("game_config", "club_war_member_cap")
    op.drop_column("game_config", "club_war_min_members")
    op.drop_column("game_config", "club_war_duration_hours")
    op.drop_column("game_config", "club_war_start_hour")
    op.drop_column("game_config", "club_war_start_weekday")
    op.drop_column("game_config", "club_war_enabled")
    op.drop_index("ix_club_wars_status_ends_at", table_name="club_wars")
    op.drop_table("club_wars")
    op.drop_table("club_war_rounds")
    op.drop_column("clubs", "war_rating")
    # Enum values stay: Postgres can't drop enum values.
