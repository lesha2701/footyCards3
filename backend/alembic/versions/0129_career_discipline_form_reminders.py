"""Карьера: yellow/red cards, player form and the pre-round reminder —
game_config settings and the career_reminder notification type.

Revision ID: 0129
Revises: 0128
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0129"
down_revision: Union[str, None] = "0128"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'career_reminder'")
    gc = "game_config"
    op.add_column(gc, sa.Column("career_yellow_chance_pct", sa.Integer(), nullable=False, server_default="8"))
    op.add_column(gc, sa.Column("career_red_chance_pct", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(gc, sa.Column("career_yellows_for_ban", sa.Integer(), nullable=False, server_default="3"))
    op.add_column(gc, sa.Column("career_form_max", sa.Integer(), nullable=False, server_default="2"))
    op.add_column(gc, sa.Column("career_reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    gc = "game_config"
    for column in (
        "career_reminders_enabled", "career_form_max", "career_yellows_for_ban",
        "career_red_chance_pct", "career_yellow_chance_pct",
    ):
        op.drop_column(gc, column)
    # The enum value stays: Postgres can't drop enum values.
