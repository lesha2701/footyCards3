"""«Замес»: the game type, users' hourly/daily counters and best run, and the
GameConfig settings (base fee, fee per cleared wave, waves cap, daily cap).

Revision ID: 0324
Revises: 0323
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0324"
down_revision: Union[str, None] = "0323"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'zames'")
    op.add_column("users", sa.Column("zames_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("zames_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("zames_hourly_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("zames_hour_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("zames_best_knockouts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_config", sa.Column("zames_base_coins", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("zames_wave_coins", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("game_config", sa.Column("zames_max_waves", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("game_config", sa.Column("zames_daily_limit", sa.Integer(), nullable=False, server_default="5"))


def downgrade() -> None:
    for column in ("zames_daily_limit", "zames_max_waves", "zames_wave_coins", "zames_base_coins"):
        op.drop_column("game_config", column)
    for column in ("zames_best_knockouts", "zames_hour_started_at", "zames_hourly_attempts",
                   "zames_attempts_reset_at", "zames_rewarded_attempts_today"):
        op.drop_column("users", column)
    # Postgres can't drop one enum value: 'zames' stays in game_type_enum.
