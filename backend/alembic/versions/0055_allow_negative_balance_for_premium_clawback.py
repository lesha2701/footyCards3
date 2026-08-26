"""Allow negative balance_after for premium_subscription_adjustment rows

The bot's periodic clawback sweep must be able to debit a player who
unsubscribed even past zero (see docs/superpowers/specs/2026-08-26-premium-
task-coin-clawback-design.md). Every other transaction type keeps the
original non-negative invariant.

Revision ID: 0055
Revises: 0054
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "ck_coin_tx_balance_non_negative"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME, "coin_transactions", "balance_after >= 0 OR type = 'premium_subscription_adjustment'"
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(CONSTRAINT_NAME, "coin_transactions", "balance_after >= 0")
