"""«Редкие версии»: user_cards.finish and their chances in game_config

Revision ID: 0336
Revises: 0335
Create Date: 2026-11-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0336"
down_revision: Union[str, None] = "0335"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_cards", sa.Column("finish", sa.String(length=16), nullable=True))
    op.add_column("game_config", sa.Column("finish_gold_per_mille", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("game_config", sa.Column("finish_autograph_per_mille", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("finish_night_per_mille", sa.Integer(), nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("game_config", "finish_night_per_mille")
    op.drop_column("game_config", "finish_autograph_per_mille")
    op.drop_column("game_config", "finish_gold_per_mille")
    op.drop_column("user_cards", "finish")
