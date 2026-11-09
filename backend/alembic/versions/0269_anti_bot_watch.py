"""Anti-bot checks only for accounts under watch; a bot win is worth a third

«Ты здесь?» and «усталость» now apply only to users.anti_bot_watch (set in
«Антифрод»); everyone else's open checks and rests are cleared. A win over a
bot moves the rating by game_config.bot_win_rating_pct of a normal win.

Per the owner's decision (2026-11-09): tsarspartak and vadim19g88 stay under
watch, and tsarspartak's game rewards are switched off.

Revision ID: 0269
Revises: 0268
Create Date: 2026-11-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0269"
down_revision: Union[str, None] = "0268"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("anti_bot_watch", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("bot_win_rating_pct", sa.Integer(), nullable=False, server_default="33"))
    op.execute("UPDATE users SET anti_bot_watch = true WHERE username IN ('tsarspartak', 'vadim19g88')")
    op.execute("UPDATE users SET game_rewards_blocked = true WHERE username = 'tsarspartak'")
    op.execute(
        "UPDATE users SET presence_challenge = NULL, presence_due_at = NULL, rest_required_until = NULL "
        "WHERE NOT anti_bot_watch"
    )


def downgrade() -> None:
    op.drop_column("game_config", "bot_win_rating_pct")
    op.drop_column("users", "anti_bot_watch")
