"""card_offers.announced_at: when the admin sent the «new card in the shop»
message to every player (once per offer).

Revision ID: 0201
Revises: 0200
Create Date: 2026-10-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0201"
down_revision: Union[str, None] = "0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("card_offers", sa.Column("announced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("card_offers", "announced_at")
