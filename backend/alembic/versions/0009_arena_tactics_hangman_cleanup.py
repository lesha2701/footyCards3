"""arena tactics, football hangman, remove match energy, unrestricted pack delete

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'football_hangman'")

    # Card Arena tactics
    op.add_column("lineups", sa.Column("tactic", sa.String(16), nullable=False, server_default="balanced"))

    # Allow deleting a pack even if it has opening history — the history
    # (and its per-card log rows, which cascade further) is deleted along
    # with the pack instead of blocking the operation.
    op.drop_constraint("pack_openings_pack_id_fkey", "pack_openings", type_="foreignkey")
    op.create_foreign_key(
        "pack_openings_pack_id_fkey", "pack_openings", "packs", ["pack_id"], ["id"], ondelete="CASCADE"
    )

    # Football Hangman
    op.add_column("users", sa.Column("hangman_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("hangman_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("hangman_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("hangman_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("hangman_daily_limit", sa.Integer(), nullable=False, server_default="8"))
    op.add_column("game_config", sa.Column("hangman_reward_correct", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("hangman_max_wrong", sa.Integer(), nullable=False, server_default="6"))

    # Remove Card Arena energy — the existing hourly play limit is enough
    op.drop_column("users", "match_energy")
    op.drop_column("users", "match_energy_reset_at")
    op.drop_column("game_config", "match_daily_energy")


def downgrade() -> None:
    op.add_column("game_config", sa.Column("match_daily_energy", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("users", sa.Column("match_energy_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("match_energy", sa.Integer(), nullable=False, server_default="10"))

    op.drop_column("game_config", "hangman_max_wrong")
    op.drop_column("game_config", "hangman_reward_correct")
    op.drop_column("game_config", "hangman_daily_limit")
    op.drop_column("users", "hangman_hour_started_at")
    op.drop_column("users", "hangman_hourly_attempts")
    op.drop_column("users", "hangman_attempts_reset_at")
    op.drop_column("users", "hangman_rewarded_attempts_today")

    op.drop_constraint("pack_openings_pack_id_fkey", "pack_openings", type_="foreignkey")
    op.create_foreign_key(
        "pack_openings_pack_id_fkey", "pack_openings", "packs", ["pack_id"], ["id"], ondelete="RESTRICT"
    )

    op.drop_column("lineups", "tactic")

    # Note: Postgres has no clean "ALTER TYPE ... DROP VALUE" — the
    # 'football_hangman' value added to game_type_enum in upgrade() is
    # intentionally left in place on downgrade.
