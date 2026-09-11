"""Per-match club budget rewards — ClubBudgetTransactionType.tournament_match_reward,
GameConfig.club_match_reward_win/draw/loss

Revision ID: 0102
Revises: 0101
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0102"
down_revision: Union[str, None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'tournament_match_reward'")

    op.add_column("game_config", sa.Column("club_match_reward_win", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("game_config", sa.Column("club_match_reward_draw", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("club_match_reward_loss", sa.Integer(), nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("game_config", "club_match_reward_loss")
    op.drop_column("game_config", "club_match_reward_draw")
    op.drop_column("game_config", "club_match_reward_win")
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
