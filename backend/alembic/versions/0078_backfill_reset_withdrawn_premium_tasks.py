"""Backfill: reset already-withdrawn premium tasks to claimable again

Premium task clawback used to auto-restore coins silently on resubscribe,
leaving the task permanently marked reward_claimed=true. That design just
changed to a manual reclaim flow: a clawed-back task resets to its
pre-claim state (reward_claimed=false, reward_coins_granted=NULL,
coins_withdrawn=false) so the player has to resubscribe and press "get
reward" again. Rows already sitting in the old withdrawn state (coins
already debited, reward_claimed still true) need the same reset applied
once here, or they'd never be picked up by the sweep again (it only acts
on unsubscribe transitions) and the player would stay stuck.

Revision ID: 0078
Revises: 0077
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0078"
down_revision: Union[str, None] = "0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE user_tasks SET reward_claimed = false, reward_coins_granted = NULL, coins_withdrawn = false "
        "WHERE reward_claimed = true AND coins_withdrawn = true"
    )


def downgrade() -> None:
    # Data-only backfill — the coin debit that already happened stays either
    # way, and there's no way to know which rows this touched to reverse it.
    pass
