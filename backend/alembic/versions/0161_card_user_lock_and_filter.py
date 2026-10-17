"""user_cards.is_user_locked + users.card_filter_default

Revision ID: 0161
Revises: 0160
Create Date: 2026-10-17

* `user_cards.is_user_locked` — the owner's own «замок»: a locked copy can't
  be sold (single, bulk, «Продать дубликаты») or burned as material (stars,
  diamond feeding, Academy prestige, the Forge). It still plays and trades.
* `users.card_filter_default` — the player's saved default card filter
  (rarity / country / club / position / sort), applied when the collection,
  album and Forge open.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0161"
down_revision: Union[str, None] = "0160"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_cards", sa.Column("is_user_locked", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column("users", sa.Column("card_filter_default", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "card_filter_default")
    op.drop_column("user_cards", "is_user_locked")
