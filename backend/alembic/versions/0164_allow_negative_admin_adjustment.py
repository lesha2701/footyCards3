"""Allow an admin adjustment to take a balance below zero

Coins bought from multi-account farms were already spent, so taking them
back has to leave the buyer with a debt (negative balance) that future
earnings pay off — 0076 only allowed that for the premium clawback.
Debits of every other type still require balance_after >= 0.

Revision ID: 0164
Revises: 0163
Create Date: 2026-10-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0164"
down_revision: Union[str, None] = "0163"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "ck_coin_tx_balance_non_negative"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME, "coin_transactions",
        "balance_after >= 0 OR type IN ('premium_subscription_adjustment', 'admin_adjustment') OR amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME, "coin_transactions",
        "balance_after >= 0 OR type = 'premium_subscription_adjustment' OR amount >= 0",
    )
