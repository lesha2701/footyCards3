"""Cap diamond-rarity cards to 1 per Tactico squad and per Card Arena lineup

Revision ID: 0084
Revises: 0083
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("tactico_max_diamond_cards", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("game_config", sa.Column("match_max_diamond_cards", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("game_config", "match_max_diamond_cards")
    op.drop_column("game_config", "tactico_max_diamond_cards")
