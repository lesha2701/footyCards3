"""«Задания»: day and week sets with activity points and chests.

task_definitions get `period` (daily / weekly), `points` (activity) and an
optional `route` («Играть →») and `is_required` (a pinned must-do premium
subscription — premium channel tasks now pay 3000); user_tasks get `period_key` (the day / week
the instance belongs to). New tables: task_activity (points and free
replacements per period), task_chest_claims (one row per opened chest).
GameConfig: slot counts, free replacements and both chest tracks. Four weekly
tasks on the existing metrics are added (by code, never twice).

Revision ID: 0211
Revises: 0210
Create Date: 2026-10-27
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0211"
down_revision: Union[str, None] = "0210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DAILY_CHESTS = [{"points": 20, "coins": 100}, {"points": 50, "coins": 200}, {"points": 80, "coins": 300},
                {"points": 100, "coins": 500, "card_rarity": "rare"}]
WEEKLY_CHESTS = [{"points": 30, "coins": 500}, {"points": 60, "coins": 1000},
                 {"points": 90, "coins": 1500, "card_rarity": "epic"}]
# code, name, description, metric, target, coins, route
WEEKLY_TASKS = [
    ("weekly_packs_10", "Коллекционер недели", "Открой 10 паков за неделю", "packs_opened", 10, 600, "/packs"),
    ("weekly_memory_25", "Феноменальная память", "Пройди 25 уровней Memory за неделю", "memory_levels_completed", 25, 600, "/play/memory"),
    ("weekly_fan_20", "Самый преданный фанат", "Пройди 20 рядов в «Футбольном фанате» за неделю", "saboteur_levels_cleared", 20, 600, "/play/saboteur"),
    ("weekly_arena_3", "Стена в обороне", "Выиграй 3 матча Card Arena всухую за неделю", "arena_clean_sheet_wins", 3, 700, "/play/arena"),
]


def upgrade() -> None:
    op.add_column("task_definitions", sa.Column("period", sa.String(8), nullable=False, server_default="daily"))
    op.add_column("task_definitions", sa.Column("points", sa.Integer(), nullable=False, server_default="20"))
    op.add_column("task_definitions", sa.Column("route", sa.String(64), nullable=True))
    op.add_column("task_definitions", sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_tasks", sa.Column("period_key", sa.String(10), nullable=True))
    op.create_table(
        "task_activity",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period_key", sa.String(10), primary_key=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rerolls", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "task_chest_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("period_key", sa.String(10), nullable=False),
        sa.Column("chest_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "period_key", "chest_index", name="uq_task_chest_claim"),
    )
    op.add_column("game_config", sa.Column("task_daily_slots", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("task_weekly_slots", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("game_config", sa.Column("task_free_rerolls", sa.Integer(), nullable=False, server_default="1"))
    for name, value in (("task_daily_chests", DAILY_CHESTS), ("task_weekly_chests", WEEKLY_CHESTS)):
        op.add_column("game_config", sa.Column(
            name, sa.JSON(), nullable=False, server_default=sa.text("'" + json.dumps(value) + "'::json"),
        ))

    # Channel subscriptions pay more: 3000 for future claims (already paid ones keep what they got).
    op.execute(
        "UPDATE task_definitions SET reward_coins = 3000 WHERE category = 'premium' AND reward_coins < 3000 "
        "AND (channel_username IS NOT NULL OR channel_chat_id IS NOT NULL)"
    )

    # The game chat (its invite link used to sit on the home page) is a must-do subscription.
    op.execute(
        "UPDATE task_definitions SET is_required = true WHERE category = 'premium' "
        "AND invite_link LIKE '%42EZisiOi8w1ZmMy%'"
    )

    bind = op.get_bind()
    existing = set(bind.execute(sa.text("SELECT code FROM task_definitions")).scalars())
    for i, (code, name, description, metric, target, coins, route) in enumerate(WEEKLY_TASKS):
        if code in existing:
            continue
        bind.execute(sa.text(
            "INSERT INTO task_definitions (code, name, description, category, condition_type, metric, target_value, "
            "reward_coins, reward_skill_tokens, is_active, sort_order, period, points, route, created_at, updated_at) "
            "VALUES (:code, :name, :description, 'regular', 'metric_counter', :metric, :target, :coins, 0, true, :sort, "
            "'weekly', 30, :route, now(), now())"
        ), {"code": code, "name": name, "description": description, "metric": metric, "target": target,
            "coins": coins, "sort": 100 + i, "route": route})


def downgrade() -> None:
    op.execute("DELETE FROM task_definitions WHERE code IN (" + ", ".join(f"'{t[0]}'" for t in WEEKLY_TASKS) + ")")
    for name in ("task_weekly_chests", "task_daily_chests", "task_free_rerolls", "task_weekly_slots", "task_daily_slots"):
        op.drop_column("game_config", name)
    op.drop_table("task_chest_claims")
    op.drop_table("task_activity")
    op.drop_column("user_tasks", "period_key")
    op.drop_column("task_definitions", "is_required")
    op.drop_column("task_definitions", "route")
    op.drop_column("task_definitions", "points")
    op.drop_column("task_definitions", "period")
