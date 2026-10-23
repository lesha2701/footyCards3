"""«Стена клуба»: member posts, bot-delivered manager announcements, pins
and a per-member unread marker.

Revision ID: 0172
Revises: 0171
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0172"
down_revision: Union[str, None] = "0171"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_announcement'")
    op.create_table(
        "club_posts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("is_announcement", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_club_posts_club_id_id", "club_posts", ["club_id", "id"])
    op.add_column("club_members", sa.Column("wall_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column(
        "club_announcement_cooldown_minutes", sa.Integer(), nullable=False, server_default="60",
    ))


def downgrade() -> None:
    op.drop_column("game_config", "club_announcement_cooldown_minutes")
    op.drop_column("club_members", "wall_seen_at")
    op.drop_index("ix_club_posts_club_id_id", table_name="club_posts")
    op.drop_table("club_posts")
    # The enum value stays: Postgres can't drop enum values.
