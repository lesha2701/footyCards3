"""Карьера тренера (8-team, 14-round weekly seasons, optionally with a friend)
and friends: tables, game_config settings, notification/transaction enum
values and the "career_champion" trophy definition.

Revision ID: 0128
Revises: 0127
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0128"
down_revision: Union[str, None] = "0127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOTIFICATION_TYPES = (
    "friend_request", "friend_accepted", "career_invite", "career_round_result", "career_season_finished",
)


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    for value in _NOTIFICATION_TYPES:
        op.execute(f"ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'career_reward'")

    op.create_table(
        "career_seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="pro"),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rounds_played", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_career_seasons_status", "career_seasons", ["status"])
    op.create_index("ix_career_seasons_creator_id", "career_seasons", ["creator_id"])

    op.create_table(
        "career_participants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("career_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="accepted"),
        sa.Column("squad_card_ids", sa.JSON(), nullable=False, server_default=_json("[]")),
        sa.Column("lineup", sa.JSON(), nullable=True),
        sa.Column("formation", sa.String(16), nullable=False, server_default="4-3-3"),
        sa.Column("mentality", sa.String(16), nullable=False, server_default="BALANCED"),
        sa.Column("playstyle", sa.String(16), nullable=False, server_default="CENTRAL_PLAY"),
        sa.Column("condition", sa.JSON(), nullable=False, server_default=_json("{}")),
        sa.Column("final_place", sa.Integer(), nullable=True),
        sa.Column("coins_earned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("season_id", "user_id", name="uq_career_participant"),
    )
    op.create_index("ix_career_participants_season", "career_participants", ["season_id"])
    op.create_index("ix_career_participants_user_id", "career_participants", ["user_id"])

    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addressee_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_low", sa.Integer(), nullable=False),
        sa.Column("user_high", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_low", "user_high", name="uq_friendship_pair"),
    )
    op.create_index("ix_friendships_requester_id", "friendships", ["requester_id"])
    op.create_index("ix_friendships_addressee_id", "friendships", ["addressee_id"])

    gc = "game_config"
    op.add_column(gc, sa.Column("career_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(gc, sa.Column("career_place_rewards", sa.JSON(), nullable=False,
                                server_default=_json("[1500, 1000, 700, 500, 350, 250, 150, 100]")))
    op.add_column(gc, sa.Column("career_difficulty_reward_pct", sa.JSON(), nullable=False, server_default=_json("[100, 150, 200]")))
    op.add_column(gc, sa.Column("career_difficulty_rating_offset", sa.JSON(), nullable=False, server_default=_json("[-6, 0, 4]")))
    op.add_column(gc, sa.Column("career_match_reward_win", sa.Integer(), nullable=False, server_default="30"))
    op.add_column(gc, sa.Column("career_match_reward_draw", sa.Integer(), nullable=False, server_default="10"))
    op.add_column(gc, sa.Column("career_bot_growth_tenths", sa.Integer(), nullable=False, server_default="3"))
    op.add_column(gc, sa.Column("career_fatigue_per_match", sa.Integer(), nullable=False, server_default="35"))
    op.add_column(gc, sa.Column("career_fatigue_recovery", sa.Integer(), nullable=False, server_default="40"))
    op.add_column(gc, sa.Column("career_fatigue_penalty_pct", sa.Integer(), nullable=False, server_default="15"))
    op.add_column(gc, sa.Column("career_injury_chance_pct", sa.Integer(), nullable=False, server_default="3"))

    # Champion trophy, granted automatically by career_service on a 1st place.
    op.execute(
        "INSERT INTO trophy_definitions (code, name, description, icon, is_active, sort_order) "
        "SELECT 'career_champion', 'Чемпион карьеры', 'Выиграл сезон в режиме «Карьера тренера»', '🏆', true, 0 "
        "WHERE NOT EXISTS (SELECT 1 FROM trophy_definitions WHERE code = 'career_champion')"
    )


def downgrade() -> None:
    gc = "game_config"
    for column in (
        "career_injury_chance_pct", "career_fatigue_penalty_pct", "career_fatigue_recovery", "career_fatigue_per_match",
        "career_bot_growth_tenths", "career_match_reward_draw", "career_match_reward_win",
        "career_difficulty_rating_offset", "career_difficulty_reward_pct", "career_place_rewards", "career_enabled",
    ):
        op.drop_column(gc, column)
    op.drop_table("friendships")
    op.drop_table("career_participants")
    op.drop_table("career_seasons")
    # Enum values and the trophy definition are left in place on purpose:
    # Postgres can't drop enum values, and granted trophies reference the row.
