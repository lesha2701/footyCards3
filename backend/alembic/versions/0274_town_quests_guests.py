"""«Город»: residents' quests (user_town_quests), guests with likes and gifts
(town_visits, user_towns.gifts_pending) and their numbers
(game_config.town_social over town_social_service.SOCIAL_DEFAULTS).

Revision ID: 0274
Revises: 0273
Create Date: 2026-11-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0274"
down_revision: Union[str, None] = "0273"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for value in ("town_quest", "town_gift"):
            op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")
    op.add_column("user_towns", sa.Column("gifts_pending", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_config", sa.Column("town_social", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "user_town_quests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("baseline", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("resident_id", sa.Integer(), sa.ForeignKey("town_residents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "day", "slot", name="uq_user_town_quest_slot"),
    )
    op.create_table(
        "town_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("visitor_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("day", sa.Date(), nullable=False, index=True),
        sa.Column("liked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("gift_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("visitor_id", "owner_id", "day", name="uq_town_visit_day"),
    )


def downgrade() -> None:
    op.drop_table("town_visits")
    op.drop_table("user_town_quests")
    op.drop_column("game_config", "town_social")
    op.drop_column("user_towns", "gifts_pending")
