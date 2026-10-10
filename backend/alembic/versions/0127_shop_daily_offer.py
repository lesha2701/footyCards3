"""Shop "предложение дня": config on game_config (off by default) and the
per-player claimed-on date.

Revision ID: 0127
Revises: 0126
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0127"
down_revision: Union[str, None] = "0126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("shop_daily_offer_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("shop_daily_offer_discount_pct", sa.Integer(), nullable=False, server_default="25"))
    op.add_column("game_config", sa.Column("shop_daily_offer_pack_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("daily_offer_claimed_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "daily_offer_claimed_on")
    op.drop_column("game_config", "shop_daily_offer_pack_id")
    op.drop_column("game_config", "shop_daily_offer_discount_pct")
    op.drop_column("game_config", "shop_daily_offer_enabled")
