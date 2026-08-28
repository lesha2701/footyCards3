"""Add premium_task_coins_withdrawn/restored to notification_type_enum

The clawback sweep (bot/services/premium_subscription_check.py) adjusted the
player's balance and the task's coins_withdrawn flag on every subscription
transition, but never told the player anything happened — they'd just see
their balance change with no explanation. These two types back a new
Notification row the sweep now creates on each transition.

Revision ID: 0077
Revises: 0076
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0077"
down_revision: Union[str, None] = "0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'premium_task_coins_withdrawn'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'premium_task_coins_restored'")


def downgrade() -> None:
    # Postgres has no clean "ALTER TYPE ... DROP VALUE" — same accepted
    # asymmetric-downgrade limitation as every prior enum-value addition
    # in this codebase (see 0002_tasks_and_minigames.py's identical note).
    pass
