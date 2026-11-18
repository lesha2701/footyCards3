"""«Основная копия»: the owner picks which copy of a player plays and levels
up (user_cards.is_main, at most one per owner and player).

Revision ID: 0314
Revises: 0313
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0314"
down_revision: Union[str, None] = "0313"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(
        "uq_user_cards_owner_player_main", "user_cards", ["owner_id", "player_id"], unique=True,
        postgresql_where=sa.text("is_main"),
    )


def downgrade() -> None:
    op.drop_index("uq_user_cards_owner_player_main", table_name="user_cards")
    op.drop_column("user_cards", "is_main")
