""""Лига клубов": weekly club activity table with budget rewards; who caused
each club budget movement (club_budget_transactions.user_id) for the admin
spending history.

Revision ID: 0134
Revises: 0133
Create Date: 2026-10-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0134"
down_revision: Union[str, None] = "0133"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE club_budget_transaction_type_enum ADD VALUE IF NOT EXISTS 'league_reward'")
    op.execute("ALTER TYPE notification_type_enum ADD VALUE IF NOT EXISTS 'club_league_reward'")

    op.create_table(
        "club_league_weeks",
        sa.Column("week_start", sa.Date(), primary_key=True),
        sa.Column("is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "club_league_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "week_start", sa.Date(), sa.ForeignKey("club_league_weeks.week_start", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reward", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("week_start", "club_id", name="uq_club_league_result_week_club"),
    )
    op.create_index("ix_club_league_results_week_start", "club_league_results", ["week_start"])
    op.create_index("ix_club_league_results_club_id", "club_league_results", ["club_id"])

    gc = "game_config"
    op.add_column(gc, sa.Column("club_league_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    for name, default in (
        ("club_league_points_game", "2"), ("club_league_points_pack", "5"),
        ("club_league_points_task", "3"), ("club_league_member_weekly_cap", "200"),
    ):
        op.add_column(gc, sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column(gc, sa.Column(
        "club_league_rewards", sa.JSON(), nullable=False,
        server_default=sa.text("'[1500, 1000, 750, 500, 400, 300, 200, 150, 100, 100]'::json"),
    ))

    op.add_column(
        "club_budget_transactions",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # Best-effort backfill of who caused past movements: club mini-game
    # rewards point at their game session; club pack purchases are matched to
    # the opening written in the same request (same club and pack, closest
    # timestamp within a few seconds).
    op.execute(
        """
        UPDATE club_budget_transactions t SET user_id = gs.user_id
        FROM game_sessions gs
        WHERE t.related_object_type = 'game_session' AND gs.id = t.related_object_id
        """
    )
    op.execute(
        """
        UPDATE club_budget_transactions t SET user_id = (
            SELECT o.opened_by_user_id FROM club_pack_openings o
            WHERE o.club_id = t.club_id AND o.club_pack_id = t.related_object_id
              AND abs(extract(epoch FROM (o.created_at - t.created_at))) < 10
            ORDER BY abs(extract(epoch FROM (o.created_at - t.created_at)))
            LIMIT 1
        )
        WHERE t.type = 'pack_purchase' AND t.user_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("club_budget_transactions", "user_id")
    for name in (
        "club_league_rewards", "club_league_member_weekly_cap", "club_league_points_task",
        "club_league_points_pack", "club_league_points_game", "club_league_enabled",
    ):
        op.drop_column("game_config", name)
    op.drop_index("ix_club_league_results_club_id", table_name="club_league_results")
    op.drop_index("ix_club_league_results_week_start", table_name="club_league_results")
    op.drop_table("club_league_results")
    op.drop_table("club_league_weeks")
    # Enum values stay (Postgres cannot drop one) — same accepted asymmetry
    # as every earlier enum-value addition.
