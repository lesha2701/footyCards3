"""Trade anti-farming: who may give value in a trade, a daily cap on coins
received through trades, an optional coin tax, and the thresholds of the
admin «suspicious trade flows» report.

Revision ID: 0165
Revises: 0164
Create Date: 2026-10-16

Every new Telegram account starts with coins and free packs, and trades let
anyone hand coins/cards to anyone — so throwaway accounts could funnel their
starter value into one main account.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0165"
down_revision: Union[str, None] = "0164"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("trade_send_min_account_age_days", "3"),
    ("trade_send_min_active_days", "2"),
    ("trade_daily_coins_receive_cap", "3000"),
    ("trade_coin_tax_pct", "0"),
    ("trade_suspicious_young_days", "14"),
    ("trade_suspicious_min_donors", "3"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'trade_coin_tax'")
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
    # The enum value stays: Postgres can't drop enum values.
