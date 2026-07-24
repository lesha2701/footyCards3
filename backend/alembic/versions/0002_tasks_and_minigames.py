"""tasks system and 3 new minigames

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

task_category_enum = postgresql.ENUM("regular", "premium", name="task_category_enum", create_type=False)
task_condition_type_enum = postgresql.ENUM(
    "metric_counter", "match_min_rating", name="task_condition_type_enum", create_type=False
)

NEW_ENUMS = [task_category_enum, task_condition_type_enum]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'saboteur'")
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'penalty'")
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'free_kick'")
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'task'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'task_reward'")

    op.drop_table("user_achievements")
    op.drop_table("achievements")

    op.create_table(
        "task_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("category", task_category_enum, nullable=False, server_default="regular"),
        sa.Column("condition_type", task_condition_type_enum, nullable=False),
        sa.Column("metric", sa.String(64), nullable=True),
        sa.Column("target_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("condition_params", sa.JSON(), nullable=True),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reward_pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel_username", sa.String(128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_task_definitions_code"),
    )

    op.create_table(
        "user_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "task_definition_id", sa.Integer(), sa.ForeignKey("task_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_index", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "task_definition_id", name="uq_user_task"),
    )
    op.create_index("ix_user_tasks_user_id", "user_tasks", ["user_id"])
    op.create_index("ix_user_tasks_task_definition_id", "user_tasks", ["task_definition_id"])
    op.create_index(
        "uq_user_task_slot", "user_tasks", ["user_id", "slot_index"], unique=True,
        postgresql_where=sa.text("slot_index IS NOT NULL"),
    )

    op.add_column("game_config", sa.Column("saboteur_cell_reward", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("saboteur_daily_limit", sa.Integer(), nullable=False, server_default="10"))
    op.add_column("game_config", sa.Column("penalty_reward_win", sa.Integer(), nullable=False, server_default="150"))
    op.add_column("game_config", sa.Column("penalty_reward_draw", sa.Integer(), nullable=False, server_default="60"))
    op.add_column("game_config", sa.Column("penalty_reward_loss", sa.Integer(), nullable=False, server_default="15"))
    op.add_column("game_config", sa.Column("penalty_bot_miss_chance", sa.Numeric(4, 2), nullable=False, server_default="0.12"))
    op.add_column("game_config", sa.Column("penalty_daily_limit", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("game_config", sa.Column("free_kick_period_min_ms", sa.Integer(), nullable=False, server_default="1100"))
    op.add_column("game_config", sa.Column("free_kick_period_max_ms", sa.Integer(), nullable=False, server_default="1700"))
    op.add_column("game_config", sa.Column("free_kick_base_stake", sa.Integer(), nullable=False, server_default="40"))
    op.add_column("game_config", sa.Column("free_kick_daily_limit", sa.Integer(), nullable=False, server_default="8"))

    op.add_column("users", sa.Column("saboteur_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("saboteur_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("penalty_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("penalty_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("free_kick_rewarded_attempts_today", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("free_kick_attempts_reset_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Note: Postgres has no clean "ALTER TYPE ... DROP VALUE" — the enum
    # values added to game_type_enum/card_source_enum/transaction_type_enum
    # in upgrade() are intentionally left in place on downgrade.
    op.drop_column("users", "free_kick_attempts_reset_at")
    op.drop_column("users", "free_kick_rewarded_attempts_today")
    op.drop_column("users", "penalty_attempts_reset_at")
    op.drop_column("users", "penalty_rewarded_attempts_today")
    op.drop_column("users", "saboteur_attempts_reset_at")
    op.drop_column("users", "saboteur_rewarded_attempts_today")

    op.drop_column("game_config", "free_kick_daily_limit")
    op.drop_column("game_config", "free_kick_base_stake")
    op.drop_column("game_config", "free_kick_period_max_ms")
    op.drop_column("game_config", "free_kick_period_min_ms")
    op.drop_column("game_config", "penalty_daily_limit")
    op.drop_column("game_config", "penalty_bot_miss_chance")
    op.drop_column("game_config", "penalty_reward_loss")
    op.drop_column("game_config", "penalty_reward_draw")
    op.drop_column("game_config", "penalty_reward_win")
    op.drop_column("game_config", "saboteur_daily_limit")
    op.drop_column("game_config", "saboteur_cell_reward")

    op.drop_table("user_tasks")
    op.drop_table("task_definitions")

    op.create_table(
        "achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("reward_coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_value", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("metric", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_achievements_code"),
    )
    op.create_table(
        "user_achievements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", sa.Integer(), sa.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
