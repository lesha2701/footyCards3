"""fix referral reward flow

Fixes a production crash: `NotificationType.referral_joined` existed in the
Python enum but was never added to the Postgres `notification_type_enum`
type, so every attempt to notify a referrer (inside `pack_service.open_pack`)
raised `InvalidTextRepresentationError` and rolled back the whole pack
purchase — referred users could not open a paid pack at all.

Also adds the columns needed to pay out direct coin rewards for referrals
(200 to the referred user, 400 to the referrer) the first time the referred
user opens ANY pack (paid or free), gated by a dedicated one-shot flag
instead of the previous fragile "count of paid pack openings == 1" check.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'referral_joined'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'referral_reward'")

    op.add_column(
        "users", sa.Column("referral_reward_granted", sa.Boolean(), nullable=False, server_default="false")
    )
    op.add_column(
        "game_config", sa.Column("referral_referred_reward", sa.Integer(), nullable=False, server_default="200")
    )
    op.add_column(
        "game_config", sa.Column("referral_referrer_reward", sa.Integer(), nullable=False, server_default="400")
    )


def downgrade() -> None:
    op.drop_column("game_config", "referral_referrer_reward")
    op.drop_column("game_config", "referral_referred_reward")
    op.drop_column("users", "referral_reward_granted")
    # Postgres cannot drop a single value from an enum type — the two
    # ADD VALUEs above are not reversible.
