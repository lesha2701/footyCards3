"""Premium task coin clawback: per-claim reward snapshot + withdrawal state

Revision ID: 0054
Revises: 0053
Create Date: 2026-08-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0054"
down_revision: Union[str, None] = "0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'premium_subscription_adjustment'")
    op.add_column("user_tasks", sa.Column("reward_coins_granted", sa.Integer(), nullable=True))
    op.add_column(
        "user_tasks", sa.Column("coins_withdrawn", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("user_tasks", "coins_withdrawn")
    op.drop_column("user_tasks", "reward_coins_granted")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving the new enum value
    # in place on downgrade is harmless (mirrors every prior migration's
    # same note).
