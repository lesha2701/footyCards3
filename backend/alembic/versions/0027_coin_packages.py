"""Replace the formula-based Stars-to-coins rate (GameConfig.stars_to_coins_rate
and friends) with admin-defined discrete CoinPackage denominations.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

coin_packages_table = sa.table(
    "coin_packages",
    sa.column("stars_price", sa.Integer),
    sa.column("coins_amount", sa.Integer),
    sa.column("is_active", sa.Boolean),
    sa.column("sort_order", sa.Integer),
)


def upgrade() -> None:
    op.create_table(
        "coin_packages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stars_price", sa.Integer(), nullable=False),
        sa.Column("coins_amount", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seed with the equivalent of the old default formula (rate=2,
    # bulk_threshold=50, bulk_bonus_pct=0.10) so existing purchase amounts
    # don't change until an admin edits them.
    op.bulk_insert(
        coin_packages_table,
        [
            {"stars_price": 10, "coins_amount": 20, "is_active": True, "sort_order": 0},
            {"stars_price": 25, "coins_amount": 50, "is_active": True, "sort_order": 1},
            {"stars_price": 50, "coins_amount": 110, "is_active": True, "sort_order": 2},
            {"stars_price": 100, "coins_amount": 220, "is_active": True, "sort_order": 3},
        ],
    )

    op.drop_column("game_config", "stars_bulk_bonus_pct")
    op.drop_column("game_config", "stars_bulk_threshold")
    op.drop_column("game_config", "stars_to_coins_rate")


def downgrade() -> None:
    op.add_column("game_config", sa.Column("stars_to_coins_rate", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("game_config", sa.Column("stars_bulk_threshold", sa.Integer(), nullable=False, server_default="50"))
    op.add_column(
        "game_config", sa.Column("stars_bulk_bonus_pct", sa.Numeric(4, 2), nullable=False, server_default="0.10")
    )

    op.drop_table("coin_packages")
