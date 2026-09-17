"""Track which users have blocked the bot, so broadcasts/gifts/notifications
stop queuing Telegram messages for them (set by the bot on
TelegramForbiddenError, cleared on their next /start).

Revision ID: 0112
Revises: 0114
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0112"
down_revision: Union[str, None] = "0114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bot_blocked", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "bot_blocked")
