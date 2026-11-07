"""«Подарок за возвращение» and the link a player came from.

Revision ID: 0265
Revises: 0264
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0265"
down_revision: Union[str, None] = "0264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("game_config", sa.Column("comeback_gift_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("comeback_gift_days", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("game_config", sa.Column("comeback_gift_cooldown_days", sa.Integer(), nullable=False, server_default="30"))
    op.add_column("game_config", sa.Column("comeback_gift_coins", sa.Integer(), nullable=False, server_default="3000"))
    op.add_column("game_config", sa.Column("comeback_gift_pack_slug", sa.String(), nullable=False, server_default="elite"))
    # The legendary coin pack: packs are made in the admin panel, so find the
    # one that names itself legendary (else the seed's top coin pack, «elite»).
    op.execute(
        """UPDATE game_config SET comeback_gift_pack_slug = COALESCE((
               SELECT slug FROM packs
               WHERE is_active AND stars_price IS NULL
                 AND (lower(slug) LIKE '%legend%' OR lower(name) LIKE '%legend%' OR lower(name) LIKE '%леген%')
               ORDER BY id LIMIT 1
           ), 'elite')"""
    )
    op.add_column("users", sa.Column("comeback_gift_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("acquisition_source", sa.String(length=64), nullable=True))
    op.create_index("ix_users_acquisition_source", "users", ["acquisition_source"])
    op.create_table(
        "comeback_gifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gift_date", sa.Date(), nullable=False),
        sa.Column("days_away", sa.Integer(), nullable=False),
        sa.Column("rewards", sa.JSON(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "gift_date", name="uq_comeback_gifts_user_date"),
    )
    op.create_index("ix_comeback_gifts_user_id", "comeback_gifts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_comeback_gifts_user_id", table_name="comeback_gifts")
    op.drop_table("comeback_gifts")
    op.drop_index("ix_users_acquisition_source", table_name="users")
    op.drop_column("users", "acquisition_source")
    op.drop_column("users", "comeback_gift_sent_at")
    for name in (
        "comeback_gift_pack_slug", "comeback_gift_coins", "comeback_gift_cooldown_days",
        "comeback_gift_days", "comeback_gift_enabled",
    ):
        op.drop_column("game_config", name)
