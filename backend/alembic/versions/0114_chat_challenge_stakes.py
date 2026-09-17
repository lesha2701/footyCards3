"""Open (chat-invite) challenges for Tactico and Penalty: a new "chat"
opponent_type, plus a stake_coins column on both match tables and the
transaction types used to lock/settle/refund stakes.

Revision ID: 0114
Revises: 0113
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0114"
down_revision: Union[str, None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tactico_opponent_type_enum ADD VALUE IF NOT EXISTS 'chat'")
    op.execute("ALTER TYPE penalty_opponent_type_enum ADD VALUE IF NOT EXISTS 'chat'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'tactico_stake_lock'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'tactico_stake_win'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'tactico_stake_refund'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'penalty_stake_lock'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'penalty_stake_win'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'penalty_stake_refund'")
    op.add_column("tactico_matches", sa.Column("stake_coins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("penalty_matches", sa.Column("stake_coins", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("penalty_matches", "stake_coins")
    op.drop_column("tactico_matches", "stake_coins")
    # Postgres has no ALTER TYPE ... DROP VALUE — the added enum values are
    # left in place on downgrade, matching this repo's own established
    # precedent (see migration 0105's downgrade for the same situation).
