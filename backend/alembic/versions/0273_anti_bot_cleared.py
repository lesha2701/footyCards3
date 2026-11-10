"""«Проверен, не бот»: accounts checked by hand leave the suspects list

Per the owner's decision (2026-11-10) tsarspartak is cleared: no watch, no
checks, rewards back on.

Revision ID: 0273
Revises: 0272
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0273"
down_revision: Union[str, None] = "0272"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("anti_bot_cleared", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "UPDATE users SET anti_bot_cleared = true, anti_bot_watch = false, game_rewards_blocked = false, "
        "presence_challenge = NULL, presence_due_at = NULL, rest_required_until = NULL "
        "WHERE username = 'tsarspartak'"
    )


def downgrade() -> None:
    op.drop_column("users", "anti_bot_cleared")
