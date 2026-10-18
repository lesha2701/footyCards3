"""«Поиск обменов»: per-player «Ищу» / «Отдаю» lists, their limits and the
«у игрока появилась карточка из твоего «Ищу»» notification.

Revision ID: 0167
Revises: 0166
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0167"
down_revision: Union[str, None] = "0166"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("trade_finder_max_wants", "10"),
    ("trade_finder_max_gives", "20"),
    ("trade_finder_active_days", "7"),
    ("trade_finder_notify_hours", "24"),
)


def upgrade() -> None:
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'trade_wish_available'")
    op.create_table(
        "trade_wishes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "player_id", "kind", name="uq_trade_wishes_user_player_kind"),
    )
    op.create_index("ix_trade_wishes_player_kind", "trade_wishes", ["player_id", "kind"])
    for column, default in COLUMNS:
        op.add_column("game_config", sa.Column(column, sa.Integer(), nullable=False, server_default=default))


def downgrade() -> None:
    for column, _default in reversed(COLUMNS):
        op.drop_column("game_config", column)
    op.drop_index("ix_trade_wishes_player_kind", table_name="trade_wishes")
    op.drop_table("trade_wishes")
    # The enum value stays: Postgres can't drop enum values.
