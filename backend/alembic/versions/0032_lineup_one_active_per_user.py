"""Enforce at most one active lineup per user

A check-then-insert race in lineup_service._get_or_create_lineup (no row to
lock when no lineup exists yet) let two concurrent first-time requests (e.g.
picking a tactic and picking a card slot in quick succession) each create
their own "active" lineup for the same user. Every later lineup request for
that user then 500s with sqlalchemy.exc.MultipleResultsFound. This migration
deactivates any existing duplicates (keeping the one with the most cards
assigned, tie-broken by most recently created) and adds a partial unique
index so it can't happen again.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-08

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT l.id,
                   ROW_NUMBER() OVER (
                       PARTITION BY l.user_id
                       ORDER BY (SELECT COUNT(*) FROM lineup_cards lc WHERE lc.lineup_id = l.id) DESC, l.id DESC
                   ) AS rn
            FROM lineups l
            WHERE l.is_active = true
        )
        UPDATE lineups
        SET is_active = false
        WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_lineup_one_active_per_user ON lineups (user_id) WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lineup_one_active_per_user")
    # The deactivated duplicates from upgrade() are intentionally left
    # deactivated on downgrade — reactivating them would just recreate the
    # ambiguity this migration exists to fix.
