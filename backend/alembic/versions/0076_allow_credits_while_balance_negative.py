"""Allow any credit transaction while a player's balance is negative

0055 exempted premium_subscription_adjustment from the non-negative check
so the clawback sweep can debit a player past zero, but every OTHER
transaction type still required balance_after >= 0 — which meant a player
clawed back into negative balance couldn't earn ANY coins again (game
reward, task reward, daily reward, ...) until their balance crossed back to
zero on its own, since even a small positive credit still leaves
balance_after negative. Observed in production as a 500 (CheckViolationError)
on every reward claim for an affected player. Credits (amount >= 0) can never
make a balance worse, so they're now always allowed regardless of the
resulting balance; debits still require balance_after >= 0 (or the
exempted clawback type).

Revision ID: 0076
Revises: 0075
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0076"
down_revision: Union[str, None] = "0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT_NAME = "ck_coin_tx_balance_non_negative"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME, "coin_transactions",
        "balance_after >= 0 OR type = 'premium_subscription_adjustment' OR amount >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "coin_transactions", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME, "coin_transactions", "balance_after >= 0 OR type = 'premium_subscription_adjustment'"
    )
