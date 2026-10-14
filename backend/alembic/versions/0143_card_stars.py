"""«Звёзды карточек»: per-copy stars fed by duplicates of the same player,
their journal, GameConfig switch and tuning, transaction type.

Revision ID: 0143
Revises: 0142
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0143"
down_revision: Union[str, None] = "0142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DUPES = '{"common": [10, 15, 25], "rare": [10, 15, 25], "epic": [10, 15, 25], "legendary": [10, 15, 25]}'
_COINS = (
    '{"common": [100, 200, 400], "rare": [300, 600, 1200], "epic": [1000, 2000, 4000], '
    '"legendary": [3000, 6000, 12000]}'
)


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'card_star_upgrade'")

    for name in ("stars", "star_progress", "star_rating_bonus"):
        op.add_column("user_cards", sa.Column(name, sa.Integer(), nullable=False, server_default="0"))
    op.create_check_constraint(
        "ck_user_cards_stars_non_negative", "user_cards", "stars >= 0 AND star_progress >= 0 AND star_rating_bonus >= 0",
    )

    op.create_table(
        "card_star_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_card_id", sa.Integer(), sa.ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("cards_consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_card_ids", sa.JSON(), nullable=False),
        sa.Column("stars_before", sa.Integer(), nullable=False),
        sa.Column("stars_after", sa.Integer(), nullable=False),
        sa.Column("progress_before", sa.Integer(), nullable=False),
        sa.Column("progress_after", sa.Integer(), nullable=False),
        sa.Column("coins_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rating_bonus_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_card_star_ledger_user_key"),
    )
    op.create_index("ix_card_star_ledger_user_id", "card_star_ledger", ["user_id"])
    op.create_index("ix_card_star_ledger_user_card_id", "card_star_ledger", ["user_card_id"])

    op.add_column("game_config", sa.Column("card_stars_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("card_stars_max", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("card_star_dupes_per_level", sa.JSON(), nullable=False, server_default=_DUPES))
    op.add_column("game_config", sa.Column("card_star_coin_cost", sa.JSON(), nullable=False, server_default=_COINS))
    op.add_column("game_config", sa.Column("card_star_rating_per_star", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("card_star_bonus_cap", sa.Integer(), nullable=False, server_default="6"))


def downgrade() -> None:
    for name in (
        "card_star_bonus_cap", "card_star_rating_per_star", "card_star_coin_cost", "card_star_dupes_per_level",
        "card_stars_max", "card_stars_enabled",
    ):
        op.drop_column("game_config", name)
    op.drop_index("ix_card_star_ledger_user_card_id", table_name="card_star_ledger")
    op.drop_index("ix_card_star_ledger_user_id", table_name="card_star_ledger")
    op.drop_table("card_star_ledger")
    op.drop_constraint("ck_user_cards_stars_non_negative", "user_cards", type_="check")
    for name in ("star_rating_bonus", "star_progress", "stars"):
        op.drop_column("user_cards", name)
    # transaction_type_enum keeps 'card_star_upgrade' (Postgres cannot drop an
    # enum value; same as every earlier migration that added one).
