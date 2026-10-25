"""«Возвращайся»: GameConfig.bot_comeback_enabled / _days / _hour and
users.comeback_sent_at (one bot message per absence, bot/services/comeback.py).

Revision ID: 0205
Revises: 0204
Create Date: 2026-10-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0205"
down_revision: Union[str, None] = "0204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("bot_comeback_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("bot_comeback_days", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("bot_comeback_hour", sa.Integer(), nullable=False, server_default="19"))
    op.add_column("users", sa.Column("comeback_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "comeback_sent_at")
    op.drop_column("game_config", "bot_comeback_hour")
    op.drop_column("game_config", "bot_comeback_days")
    op.drop_column("game_config", "bot_comeback_enabled")
