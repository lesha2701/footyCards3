"""FUT Draft: draft a temporary squad from random cards, play up to 4
matches on a shared-difficulty ladder, leaderboard by best squad strength.

Revision ID: 0109
Revises: 0108
Create Date: 2026-09-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0109"
down_revision: Union[str, None] = "0108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'fut_draft'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'fut_draft_entry'")

    op.add_column("users", sa.Column("fut_draft_best_squad_strength", sa.Integer(), nullable=False, server_default="0"))

    op.add_column("game_config", sa.Column("fut_draft_entry_cost", sa.Integer(), nullable=False, server_default="400"))
    op.add_column("game_config", sa.Column("fut_draft_weak_chance", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("game_config", sa.Column("fut_draft_normal_chance", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("fut_draft_strong_chance", sa.Integer(), nullable=False, server_default="25"))
    op.add_column("game_config", sa.Column("fut_draft_top_chance", sa.Integer(), nullable=False, server_default="12"))
    op.add_column("game_config", sa.Column("fut_draft_jackpot_chance", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("fut_draft_reward_win_0", sa.Integer(), nullable=False, server_default="50"))
    op.add_column("game_config", sa.Column("fut_draft_reward_win_1", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("fut_draft_reward_win_2", sa.Integer(), nullable=False, server_default="350"))
    op.add_column("game_config", sa.Column("fut_draft_reward_win_3", sa.Integer(), nullable=False, server_default="700"))
    op.add_column("game_config", sa.Column("fut_draft_reward_win_4", sa.Integer(), nullable=False, server_default="1500"))


def downgrade() -> None:
    op.drop_column("game_config", "fut_draft_reward_win_4")
    op.drop_column("game_config", "fut_draft_reward_win_3")
    op.drop_column("game_config", "fut_draft_reward_win_2")
    op.drop_column("game_config", "fut_draft_reward_win_1")
    op.drop_column("game_config", "fut_draft_reward_win_0")
    op.drop_column("game_config", "fut_draft_jackpot_chance")
    op.drop_column("game_config", "fut_draft_top_chance")
    op.drop_column("game_config", "fut_draft_strong_chance")
    op.drop_column("game_config", "fut_draft_normal_chance")
    op.drop_column("game_config", "fut_draft_weak_chance")
    op.drop_column("game_config", "fut_draft_entry_cost")

    op.drop_column("users", "fut_draft_best_squad_strength")

    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'fut_draft' (GameType)
    # and 'fut_draft_entry' (TransactionType) on their enums is harmless
    # (mirrors 0030's card_pairs note).
