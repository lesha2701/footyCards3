"""Indexes on the columns that point at user_cards without one.

Deleting a card (a sale, the Forge, …) makes Postgres check every table that
references user_cards; without an index each check is a full scan of that
table — per deleted card. A sale of a few hundred duplicates scanned
penalty_matches and daily_rewards hundreds of times and held the player's
row lock for minutes. Built CONCURRENTLY: no write lock on big tables during
the deploy.

Revision ID: 0330
Revises: 0329
Create Date: 2026-11-20
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0330"
down_revision: Union[str, None] = "0329"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) — the default index=True name ix_<table>_<column>.
COLUMNS = (
    ("penalty_matches", "user_card_id"),
    ("penalty_matches", "opponent_card_id"),
    ("penalty_queue_entries", "user_card_id"),
    ("daily_rewards", "random_card_id"),
    ("wheel_spins", "user_card_id"),
    ("card_offer_purchases", "user_card_id"),
    ("card_upgrade_attempts", "result_card_id"),
    ("stars_invoices", "path_user_card_id"),
    ("academy_prospects", "mentor_card_id"),
    ("manager_clubs", "academy_card_id"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for table, column in COLUMNS:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_{table}_{column} ON {table} ({column})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for table, column in COLUMNS:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS ix_{table}_{column}")
