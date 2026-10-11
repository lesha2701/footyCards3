""""Мой игрок": my_players table, user XP columns and game_config settings.

Revision ID: 0130
Revises: 0129
Create Date: 2026-10-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0130"
down_revision: Union[str, None] = "0129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _json(value: str):
    return sa.text(f"'{value}'::json")


def upgrade() -> None:
    position = postgresql.ENUM(name="position_enum", create_type=False)
    op.create_table(
        "my_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(24), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("position", position, nullable=False),
        sa.Column("appearance", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("points_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.add_column("users", sa.Column("my_player_xp", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("my_player_xp_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("my_player_xp_day", sa.Date(), nullable=True))
    gc = "game_config"
    op.add_column(gc, sa.Column("my_player_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(gc, sa.Column("my_player_xp_per_reward", sa.Integer(), nullable=False, server_default="10"))
    op.add_column(gc, sa.Column("my_player_xp_daily_cap", sa.Integer(), nullable=False, server_default="200"))
    op.add_column(gc, sa.Column("my_player_xp_career_match", sa.Integer(), nullable=False, server_default="15"))
    op.add_column(gc, sa.Column("my_player_xp_level_base", sa.Integer(), nullable=False, server_default="100"))
    op.add_column(gc, sa.Column("my_player_xp_level_step", sa.Integer(), nullable=False, server_default="20"))
    op.add_column(gc, sa.Column("my_player_points_per_level", sa.Integer(), nullable=False, server_default="2"))
    op.add_column(gc, sa.Column("my_player_rating_cap", sa.Integer(), nullable=False, server_default="88"))
    op.add_column(gc, sa.Column("my_player_tier_thresholds", sa.JSON(), nullable=False, server_default=_json("[65, 75, 85]")))


def downgrade() -> None:
    gc = "game_config"
    for column in (
        "my_player_tier_thresholds", "my_player_rating_cap", "my_player_points_per_level",
        "my_player_xp_level_step", "my_player_xp_level_base", "my_player_xp_career_match",
        "my_player_xp_daily_cap", "my_player_xp_per_reward", "my_player_enabled",
    ):
        op.drop_column(gc, column)
    for column in ("my_player_xp_day", "my_player_xp_today", "my_player_xp"):
        op.drop_column("users", column)
    op.drop_table("my_players")
