"""Trades vs. multi-accounts and real-money deals:

- user_cards.from_free_source: the card came from a free source (calendar, tasks,
  bingo, wheel, gifts, free/bonus packs, …) — a valuable one (legendary,
  diamond, «Академия», limited) then can't leave the account. Backfilled
  for every existing card.
- trade_offers.counts_for_progress: whether an accepted trade counts for
  tasks / bingo (at most N per pair per day). Existing trades all count, so
  task baselines stay consistent.
- packs.pity_enabled: the legendary pity can be turned off per pack.
- GameConfig: «Проверенный аккаунт» bar for giving valuable cards, the
  equal-value rule and the card value table.

Revision ID: 0215
Revises: 0214
Create Date: 2026-10-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0215"
down_revision: Union[str, None] = "0214"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BOUND_SOURCES = (
    "daily_reward", "admin_grant", "achievement", "game_reward", "task", "free_pack", "newbie",
    "card_upgrade", "collection_reward", "chat_pack", "gift", "wheel", "league_reward", "club_reward",
)
INT_COLUMNS = (
    ("trade_verified_min_age_days", "3"),
    ("trade_verified_min_active_days", "0"),
    ("trade_verified_min_stars", "49"),
    ("trade_min_value_ratio_pct", "50"),
    ("trade_value_check_min", "2000"),
    ("trade_progress_pair_daily", "1"),
)
CARD_VALUES = (
    '{"legendary": 6000, "legendary_top": 12000, "legendary_top_rating": 93, '
    '"limited_legendary": 30000, "limited_legendary_scarce": 60000, "limited_epic": 10000, '
    '"limited_rare": 5000, "limited_max_copies": 50, "limited_scarce_copies": 15, '
    '"diamond": 60000, "academy": [40000, 40000, 60000, 60000, 100000], "sell_multiplier": 2}'
)


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("from_free_source", sa.Boolean(), nullable=False, server_default=sa.false()))
    sources = ", ".join(f"'{s}'" for s in BOUND_SOURCES)
    op.execute(
        f"""
        UPDATE user_cards SET from_free_source = true
        WHERE source::text IN ({sources})
           OR (source::text = 'pack' AND (source_ref_id IS NULL OR source_ref_id IN (
                SELECT id FROM pack_openings WHERE price_paid = 0)))
        """
    )

    op.add_column("trade_offers", sa.Column("counts_for_progress", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("packs", sa.Column("pity_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    for column, default in INT_COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))
    op.add_column("game_config", sa.Column("card_values", sa.JSON(), nullable=False, server_default=sa.text(f"'{CARD_VALUES}'::json")))


def downgrade() -> None:
    op.drop_column("game_config", "card_values")
    for column, _default in reversed(INT_COLUMNS):
        op.drop_column("game_config", column)
    op.drop_column("packs", "pity_enabled")
    op.drop_column("trade_offers", "counts_for_progress")
    op.drop_column("user_cards", "from_free_source")
