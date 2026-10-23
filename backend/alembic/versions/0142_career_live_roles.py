"""«Карьера тренера», part 2: player roles and man-marking on participants,
achievements / trophy cabinet / digest bookkeeping on profiles, live
half-time and achievement / digest settings on GameConfig, and the
career_digest notification type.

Revision ID: 0142
Revises: 0141
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0142"
down_revision: Union[str, None] = "0141"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("career_participants", sa.Column("roles", sa.JSON(), nullable=True))
    op.add_column("career_participants", sa.Column("marking", sa.JSON(), nullable=True))
    op.add_column("career_profiles", sa.Column("achievements", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")))
    op.add_column("game_config", sa.Column("career_live_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("career_halftime_minutes", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("career_achievement_reward", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("career_digest_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'career_digest'")


def downgrade() -> None:
    # The enum value stays (PostgreSQL can't drop one); it is unused without
    # the code that sends it.
    for column in ("career_digest_enabled", "career_achievement_reward", "career_halftime_minutes", "career_live_enabled"):
        op.drop_column("game_config", column)
    op.drop_column("career_profiles", "achievements")
    op.drop_column("career_participants", "marking")
    op.drop_column("career_participants", "roles")
