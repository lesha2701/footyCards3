"""Penalty PvP: friend-challenge shootout mode

Adds the penalty_matches table, a penalty_challenge_expiry_hours GameConfig
tunable, and the new NotificationType values used by its challenge
lifecycle. Reuses the existing match_result_enum (win/draw/loss) rather
than adding a duplicate. Does NOT add users.penalty_rating — that column
already exists as of 0039_penalty_rating.py (added by the visuals plan's
Task 1 fix, before this migration was written).

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

penalty_match_status_enum = postgresql.ENUM(
    "pending_accept", "in_progress", "finished", "declined", "cancelled", "expired",
    name="penalty_match_status_enum", create_type=False,
)
match_result_enum = postgresql.ENUM("win", "draw", "loss", name="match_result_enum", create_type=False)


def upgrade() -> None:
    penalty_match_status_enum.create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_received'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_accepted'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_declined'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_cancelled'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'penalty_challenge_expired'")

    op.add_column(
        "game_config", sa.Column("penalty_challenge_expiry_hours", sa.Integer(), nullable=False, server_default="24")
    )

    op.create_table(
        "penalty_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opponent_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_name", sa.String(128), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opponent_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", penalty_match_status_enum, nullable=False, server_default="pending_accept"),
        sa.Column("user_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opponent_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", match_result_enum, nullable=True),
        sa.Column("rating_delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_state", postgresql.JSON(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_penalty_matches_user_id", "penalty_matches", ["user_id"])
    op.create_index("ix_penalty_matches_status", "penalty_matches", ["status"])
    op.create_index("ix_penalty_matches_created_at", "penalty_matches", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_penalty_matches_created_at", table_name="penalty_matches")
    op.drop_index("ix_penalty_matches_status", table_name="penalty_matches")
    op.drop_index("ix_penalty_matches_user_id", table_name="penalty_matches")
    op.drop_table("penalty_matches")

    op.drop_column("game_config", "penalty_challenge_expiry_hours")

    penalty_match_status_enum.drop(op.get_bind(), checkfirst=True)
    # notification_type_enum ADD VALUEs above are not reversible (mirrors 0017/0036's note).
