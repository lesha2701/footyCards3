"""Stakes in open chat challenges (Тактико, Стратего, Пенальти): max stake,
staked matches per pair per day and a daily cap on stake winnings — a stake
let a main account pull coins from its own alts.

Revision ID: 0179
Revises: 0178
Create Date: 2026-10-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0179"
down_revision: Union[str, None] = "0178"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("stake_max_coins", "500"),
    ("stake_pair_daily_limit", "2"),
    ("stake_daily_profit_cap", "2000"),
)


def upgrade() -> None:
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
