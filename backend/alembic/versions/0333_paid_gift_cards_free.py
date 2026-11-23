"""Cards from gifts bought with Stars are free (tradeable), like a Stars pack

Per the owner's decision (2026-11-23) the copies already opened from such
gifts are unbound too. Admin gifts (no Stars invoice) stay bound.

Revision ID: 0333
Revises: 0332
Create Date: 2026-11-23
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0333"
down_revision: Union[str, None] = "0332"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A gift's packs are opened with idempotency keys "gift-<gift id>-<n>-<ts>"
    # (gift_service.claim_gift); a delivered Stars invoice carries gift_id.
    op.execute(
        """
        UPDATE user_cards SET from_free_source = false
        WHERE from_free_source AND source = 'gift' AND id IN (
            SELECT oc.user_card_id
            FROM pack_opening_cards oc
            JOIN pack_openings po ON po.id = oc.opening_id
            JOIN gifts g ON g.recipient_id = po.user_id AND po.idempotency_key LIKE 'gift-' || g.id || '-%'
            JOIN stars_invoices si ON si.gift_id = g.id
            WHERE oc.user_card_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    pass
