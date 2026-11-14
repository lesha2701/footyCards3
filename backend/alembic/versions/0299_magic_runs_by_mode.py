"""«Мяч и Магия»: runs counted per mode (quick / hardcore / adventure / weekly challenge),
a bought run kept for its mode and day only; the quick mode's defaults lowered;
the Магический пак at 2000 coins / 15 Stars; Stars prices at 1 ⭐ = 100 coins.

Revision ID: 0299
Revises: 0298
Create Date: 2026-11-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0299"
down_revision: Union[str, None] = "0298"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONFIG_INT_COLUMNS = (
    ("magic_hardcore_daily_limit", "1"),
    ("magic_hardcore_run_coins", "350"),
    ("magic_hardcore_run_stars", "4"),
    ("magic_hardcore_star_runs", "1"),
    ("magic_adventure_daily_limit", "1"),
    ("magic_adventure_run_coins", "450"),
    ("magic_adventure_run_stars", "5"),
    ("magic_adventure_star_runs", "1"),
)
# The quick mode and the pack: (column, old default, new default) — only a value nobody changed moves.
QUICK = (
    ("magic_daily_limit", 5, 3),
    ("magic_extra_run_coins", 300, 150),
    ("magic_extra_run_stars", 5, 2),
    ("magic_creature_pack_coins", 1500, 2000),
    ("magic_creature_pack_stars", 25, 15),
    # 1 ⭐ = 100 coins
    ("magic_retry_stars", 5, 3),
    ("magic_essence_per_star", 40, 10),
    ("magic_extra_runs_daily_limit", 5, 2),
)


def upgrade() -> None:
    for name, default in CONFIG_INT_COLUMNS:
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    for name, old, new in QUICK:
        op.alter_column("game_config", name, server_default=str(new))
        op.execute(f"UPDATE game_config SET {name} = {new} WHERE {name} = {old}")
    op.add_column("users", sa.Column("magic_runs_day", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "magic_runs_day")
    for name, old, new in QUICK:
        op.alter_column("game_config", name, server_default=str(old))
    for name, _ in reversed(CONFIG_INT_COLUMNS):
        op.drop_column("game_config", name)
