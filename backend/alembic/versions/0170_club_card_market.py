"""«Лишние карты» клуба: sell non-squad club cards into the budget or
exchange N of one rarity for one of the next.

Revision ID: 0170
Revises: 0169
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0170"
down_revision: Union[str, None] = "0169"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("club_card_sell_pct", "100"),
    ("club_card_exchange_count", "5"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE club_card_source_enum ADD VALUE IF NOT EXISTS 'exchange'")
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'card_sale'")
    op.add_column("game_config", sa.Column("club_card_market_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
    op.drop_column("game_config", "club_card_market_enabled")
    # Enum values stay: Postgres can't drop enum values.
