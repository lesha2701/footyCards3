"""Open «Трансферный рынок» with the agreed launch settings.

Revision ID: 0220
Revises: 0219
Create Date: 2026-10-30

Market open; lots 1/6/24 h auctions and 72 h «Купить сразу»; 10 % burnt fee;
raise 5 % / 10 coins; floor 10 coins on top of card value; 5 lots per agent;
anti-sniping 120 s / 120 s; anyone not banned may bid; 3 wins per seller per
day. «Агентская лицензия»: on sale, 99 ⭐ for 30 days, accounts 30+ days old
that are a «Проверенный аккаунт». Plain UPDATEs on the single config row.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0220"
down_revision: Union[str, None] = "0219"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE game_config SET "
        "auction_enabled = true, "
        "auction_durations_hours = '[1, 6, 24]'::json, "
        "auction_fixed_duration_hours = 72, "
        "auction_fee_pct = 10, "
        "auction_min_increment_pct = 5, "
        "auction_min_increment_coins = 10, "
        "auction_min_price = 10, "
        "auction_max_active_lots = 5, "
        "auction_snipe_window_seconds = 120, "
        "auction_snipe_extend_seconds = 120, "
        "auction_min_account_age_days = 0, "
        "auction_max_wins_per_seller_daily = 3, "
        "agent_license_enabled = true, "
        "agent_license_stars = 99, "
        "agent_license_days = 30, "
        "agent_license_min_account_age_days = 30, "
        "agent_license_requires_verified = true"
    )
    op.execute("ALTER TABLE game_config ALTER COLUMN auction_enabled SET DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE game_config ALTER COLUMN auction_enabled SET DEFAULT false")
    op.execute("UPDATE game_config SET auction_enabled = false")
