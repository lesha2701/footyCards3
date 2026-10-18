"""«Задания недели» клуба: shared weekly goals scaled by club size; budget
reward plus a reward every member claims.

Revision ID: 0174
Revises: 0173
Create Date: 2026-10-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0174"
down_revision: Union[str, None] = "0173"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'quest_reward'")
    templates = op.create_table(
        "club_quest_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(96), nullable=False),
        sa.Column("metric", sa.String(16), nullable=False),
        sa.Column("target_per_member", sa.Integer(), nullable=False),
        sa.Column("reward_budget", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reward_card_rarity", sa.String(16), nullable=True),
        sa.Column("reward_badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reward_cosmetic_id", sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "club_quest_completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("club_quest_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("target", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("club_id", "template_id", "week_start", name="uq_club_quest_completion_once"),
    )
    op.add_column("game_config", sa.Column("club_quests_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.bulk_insert(templates, [
        {"title": "Сыграть вместе", "metric": "games", "target_per_member": 10, "reward_budget": 1500,
         "reward_coins": 150, "sort_order": 0},
        {"title": "Открыть паки", "metric": "packs", "target_per_member": 2, "reward_budget": 2000,
         "reward_coins": 0, "reward_card_rarity": "rare", "sort_order": 1},
        {"title": "Выполнить задания", "metric": "tasks", "target_per_member": 4, "reward_budget": 1000,
         "reward_coins": 200, "sort_order": 2},
    ])


def downgrade() -> None:
    op.drop_column("game_config", "club_quests_enabled")
    op.drop_table("club_quest_completions")
    op.drop_table("club_quest_templates")
    # The enum value stays: Postgres can't drop enum values.
