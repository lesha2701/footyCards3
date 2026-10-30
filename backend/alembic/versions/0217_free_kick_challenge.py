"""«Штрафной 3D»: «Испытание дня» — one attempt per player per day, the
same positions and targets for everyone, a daily leaderboard.

Revision ID: 0217
Revises: 0216
Create Date: 2026-10-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0217"
down_revision: Union[str, None] = "0216"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG = {
    "free_kick_challenge_kicks": 5,
    "free_kick_challenge_rating": 80,
    "free_kick_challenge_coins_per_hit": 30,
    "free_kick_challenge_perfect_bonus": 150,
}


def upgrade() -> None:
    for name, default in CONFIG.items():
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=str(default)))
    op.create_table(
        "free_kick_challenge_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("game_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "day", name="uq_free_kick_challenge_user_day"),
    )
    op.create_index("ix_free_kick_challenge_entries_user_id", "free_kick_challenge_entries", ["user_id"])
    op.create_index("ix_free_kick_challenge_entries_day", "free_kick_challenge_entries", ["day"])


def downgrade() -> None:
    op.drop_index("ix_free_kick_challenge_entries_day", table_name="free_kick_challenge_entries")
    op.drop_index("ix_free_kick_challenge_entries_user_id", table_name="free_kick_challenge_entries")
    op.drop_table("free_kick_challenge_entries")
    for name in reversed(list(CONFIG)):
        op.drop_column("game_config", name)
