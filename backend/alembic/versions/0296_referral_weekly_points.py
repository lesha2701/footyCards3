"""Weekly «Пригласи друга» pays weekly points.

0241 moved the referrals_count tasks from the day set to the week set but
kept the daily 20 activity points; every other weekly task gives 30. The
tasks now give 30 (WEEKLY_POINTS), and whoever already claimed one this week
gets the difference on this week's chest track (once: the task's points are
raised in the same step, so a rerun finds nothing to top up).

Revision ID: 0296
Revises: 0295
Create Date: 2026-11-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0296"
down_revision: Union[str, None] = "0295"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WEEKLY_POINTS = 30


def upgrade() -> None:
    from app.services.task_service import week_key

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        "SELECT id, points FROM task_definitions "
        "WHERE metric = 'referrals_count' AND period = 'weekly' AND category = 'regular' AND points < :p"
    ), {"p": WEEKLY_POINTS}).fetchall()
    key = week_key()
    for task_id, points in rows:
        bind.execute(sa.text(
            "UPDATE task_activity ta SET points = ta.points + CAST(:d AS integer) "
            "FROM user_tasks ut WHERE ut.task_definition_id = :t AND ut.reward_claimed "
            "AND ut.period_key = :k AND ta.user_id = ut.user_id AND ta.period_key = ut.period_key"
        ), {"d": WEEKLY_POINTS - int(points), "t": task_id, "k": key})
        bind.execute(sa.text("UPDATE task_definitions SET points = :p WHERE id = :t"), {"p": WEEKLY_POINTS, "t": task_id})


def downgrade() -> None:
    pass  # the points stay weekly
