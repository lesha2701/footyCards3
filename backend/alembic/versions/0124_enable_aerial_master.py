"""Open the aerial_master card skill now that the match engines model an
aerial duel (Card Arena: "block" on crosses/corners; player tournaments: the
header duel on a flank attack finished in the box).

Only touches the row while it still has the closed seed values from
0122/0123, so an admin's own later choice is never overwritten.

Revision ID: 0124
Revises: 0123
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0124"
down_revision: Union[str, None] = "0123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE card_skills SET is_enabled = true, pack_drop_weight = 1 "
        "WHERE code = 'aerial_master' AND is_enabled = false AND pack_drop_weight = 0"
    )


def downgrade() -> None:
    # Closing it again only stops NEW acquisition; skills already on cards stay.
    op.execute("UPDATE card_skills SET is_enabled = false, pack_drop_weight = 0 WHERE code = 'aerial_master'")
