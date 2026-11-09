"""Anti-bot: «усталость» after a long stretch of play without a real break,
a daily cap on ranked matches in every rating mode (users.ranked_today), and
the «Ты здесь?» check every hour of continuous play (presence_service).

Players with a script playing around the clock topped the ratings and farmed
coins; a human sleeps. users.play_streak_started_at / last_play_at track the
current stretch of play (gaps shorter than anti_bot_rest_hours don't break
it); after anti_bot_max_streak_hours rewards and rating stop until the player
rests anti_bot_rest_hours (users.rest_required_until).

Revision ID: 0266
Revises: 0265
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0266"
down_revision: Union[str, None] = "0265"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("anti_bot_max_streak_hours", "20"),
    ("anti_bot_rest_hours", "4"),
    ("ranked_daily_limit", "30"),
    ("presence_check_minutes", "60"),
    ("presence_check_max_wrong", "3"),
    ("presence_check_lock_minutes", "60"),
)


def upgrade() -> None:
    for column in ("play_streak_started_at", "last_play_at", "rest_required_until"):
        op.add_column("users", sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("ranked_today", sa.JSON(), nullable=True))
    op.add_column("users", sa.Column("presence_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("presence_challenge", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("presence_check_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("anti_bot_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("weekly_rating_reset_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
    op.drop_column("game_config", "anti_bot_enabled")
    op.drop_column("game_config", "weekly_rating_reset_enabled")
    op.drop_column("game_config", "presence_check_enabled")
    op.drop_column("users", "presence_challenge")
    op.drop_column("users", "presence_due_at")
    op.drop_column("users", "ranked_today")
    for column in ("rest_required_until", "last_play_at", "play_streak_started_at"):
        op.drop_column("users", column)
