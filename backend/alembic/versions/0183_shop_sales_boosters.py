"""Shop sales boosters: a legendary pity counter for paid packs, a discount
on opening 10+ packs at once and a bonus on the first coin purchase for
Stars. All three are admin settings on GameConfig; 0 switches one off.

Revision ID: 0183
Revises: 0182
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0183"
down_revision: Union[str, None] = "0182"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_COLUMNS = ("pity_packs", "bulk10_discount_pct", "first_coin_purchase_bonus_pct")


def upgrade() -> None:
    for column in CONFIG_COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("pity_counter", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "pity_counter")
    for column in reversed(CONFIG_COLUMNS):
        op.drop_column("game_config", column)
