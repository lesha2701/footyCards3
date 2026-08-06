"""Chat mode "вкарта" command: promo pack opening from group chats

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'chat_pack'")

    op.add_column("game_config", sa.Column("chat_pack_interval_hours", sa.Integer(), nullable=False, server_default="4"))
    op.add_column("users", sa.Column("chat_pack_available_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "chat_pack_available_at")
    op.drop_column("game_config", "chat_pack_interval_hours")
    # Postgres has no ALTER TYPE ... DROP VALUE; leaving 'chat_pack' on the
    # enum on downgrade is harmless (mirrors 0023's note for 'stars_purchase').
