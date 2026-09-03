"""Bingo of the Week: recurring collective weekly event

Revision ID: 0086
Revises: 0085
Create Date: 2026-09-02

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0086"
down_revision: Union[str, None] = "0085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'bingo_reward'")

    # create_type=False on the reusable column-type object: the type itself
    # is created exactly once below (checkfirst=True), and passing the same
    # sa.Enum instance into two separate create_table calls would otherwise
    # each try to CREATE TYPE again and fail on the second with "already exists".
    bingo_goal_type_enum = postgresql.ENUM(
        "packs_opened", "legendary_drops", "tactico_matches_played", "trades_completed",
        name="bingo_goal_type_enum", create_type=False,
    )
    bingo_goal_type_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "bingo_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "bingo_goal_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("goal_type", bingo_goal_type_enum, nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "bingo_weeks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reward_resolved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("all_goals_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("week_number", name="uq_bingo_week_number"),
    )

    op.create_table(
        "bingo_week_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_id", sa.Integer(), sa.ForeignKey("bingo_weeks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("goal_type", bingo_goal_type_enum, nullable=False),
        sa.Column("target_value", sa.Integer(), nullable=False),
        sa.Column("current_value", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("week_id", "goal_type", name="uq_bingo_week_goal"),
    )
    op.create_index("ix_bingo_week_goals_week_id", "bingo_week_goals", ["week_id"])

    op.create_table(
        "bingo_week_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_id", sa.Integer(), sa.ForeignKey("bingo_weeks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("coins_granted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pack_id_granted", sa.Integer(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("week_id", "user_id", name="uq_bingo_week_reward"),
    )
    op.create_index("ix_bingo_week_rewards_week_id", "bingo_week_rewards", ["week_id"])
    op.create_index("ix_bingo_week_rewards_user_id", "bingo_week_rewards", ["user_id"])

    op.add_column("game_config", sa.Column("bingo_reward_coins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("game_config", sa.Column("bingo_reward_pack_id", sa.Integer(), nullable=True))

    op.execute("INSERT INTO bingo_state (id, is_enabled, started_at) VALUES (1, false, NULL)")


def downgrade() -> None:
    op.drop_column("game_config", "bingo_reward_pack_id")
    op.drop_column("game_config", "bingo_reward_coins")
    op.drop_table("bingo_week_rewards")
    op.drop_table("bingo_week_goals")
    op.drop_table("bingo_weeks")
    op.drop_table("bingo_goal_definitions")
    op.drop_table("bingo_state")
    sa.Enum(name="bingo_goal_type_enum").drop(op.get_bind())
    # transaction_type_enum's new value is left in place — Postgres has no
    # DROP VALUE, same convention as every other additive enum value here.
