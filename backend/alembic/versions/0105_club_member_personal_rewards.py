"""Per-member personal club-tournament match rewards — ClubMember.personal_reward_enabled,
GameConfig.club_member_match_reward_win/draw/loss, TransactionType.club_tournament_match_reward

Revision ID: 0105
Revises: 0104
Create Date: 2026-09-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0105"
down_revision: Union[str, None] = "0104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'club_tournament_match_reward'")
    op.add_column("club_members", sa.Column("personal_reward_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("game_config", sa.Column("club_member_match_reward_win", sa.Integer(), nullable=False, server_default="500"))
    op.add_column("game_config", sa.Column("club_member_match_reward_draw", sa.Integer(), nullable=False, server_default="250"))
    op.add_column("game_config", sa.Column("club_member_match_reward_loss", sa.Integer(), nullable=False, server_default="50"))


def downgrade() -> None:
    op.drop_column("game_config", "club_member_match_reward_loss")
    op.drop_column("game_config", "club_member_match_reward_draw")
    op.drop_column("game_config", "club_member_match_reward_win")
    op.drop_column("club_members", "personal_reward_enabled")
    # Postgres has no ALTER TYPE ... DROP VALUE — the added enum value is left in place on
    # downgrade, matching this repo's own established precedent (see migration 0102's downgrade
    # for the exact same situation with club_budget_transaction_type_enum).
