"""Referral tasks: weekly, a new daily «Друг в игре», back-pay.

Since 0207 a friend counts on his referral_active_days-th day of play, so a
daily «Пригласи друга» (progress from the value at the day's assignment)
could only be done if that day happened to fall on the day the task was in
the set — players invited friends and the task never counted.

- Every regular referrals_count task becomes weekly; daily slots holding
  one are freed (the next read hands out a daily task again).
- New daily task friends_active_today «Друг в игре»: a counted friend played
  today (task_service.FRIENDS_ACTIVE_TODAY), with the reward / points of the
  old daily invite task.
- Back-pay: for every friend counted since 0207 (referral_reward
  transactions «Награда за приглашение друга») the referrer gets that daily
  task's reward once, minus referral task rewards he already claimed in that
  time; a notification says so.

Revision ID: 0241
Revises: 0240
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0241"
down_revision: Union[str, None] = "0240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SINCE = "2026-10-26"  # 0207: friends count on their 3rd day of play
CODE = "friend_played_today"


def upgrade() -> None:
    bind = op.get_bind()
    daily = bind.execute(sa.text(
        "SELECT id, reward_coins, points FROM task_definitions "
        "WHERE metric = 'referrals_count' AND period = 'daily' AND category = 'regular' "
        "ORDER BY target_value, id"
    )).fetchall()
    reward = int(daily[0][1]) if daily else 50
    points = int(daily[0][2]) if daily else 20

    # Back-pay first, while the tasks are still recognisable as daily ones.
    if reward > 0:
        owed = bind.execute(sa.text(
            "WITH counted AS ("
            "  SELECT user_id, count(*) AS n FROM coin_transactions "
            "  WHERE type = 'referral_reward' AND description LIKE 'Награда за приглашение друга%' "
            f"    AND created_at >= TIMESTAMPTZ '{SINCE}' GROUP BY user_id"
            "), claimed AS ("
            "  SELECT ut.user_id, count(*) AS n FROM user_tasks ut "
            "  JOIN task_definitions td ON td.id = ut.task_definition_id "
            "  WHERE td.metric = 'referrals_count' AND ut.reward_claimed AND ut.period_key >= CAST(:since_key AS varchar) "
            "  GROUP BY ut.user_id"
            ") SELECT c.user_id, c.n - COALESCE(cl.n, 0) FROM counted c LEFT JOIN claimed cl ON cl.user_id = c.user_id "
            "WHERE c.n - COALESCE(cl.n, 0) > 0"
        ), {"since_key": SINCE}).fetchall()
        for user_id, friends in owed:
            amount = reward * int(friends)
            after = bind.execute(
                sa.text("UPDATE users SET balance = balance + CAST(:a AS integer) WHERE id = :u RETURNING balance"),
                {"a": amount, "u": user_id},
            ).scalar()
            if after is None:
                continue
            bind.execute(sa.text(
                "INSERT INTO coin_transactions (user_id, amount, balance_before, balance_after, type, description, created_at) "
                "VALUES (:u, :a, :b, :after, 'task_reward', :d, now())"
            ), {"u": user_id, "a": amount, "b": after - amount, "after": after,
                "d": f"Задание «Пригласи друга» вдогонку: {friends} × {reward}"})
            bind.execute(sa.text(
                "INSERT INTO notifications (user_id, type, title, body, is_read, telegram_sent, created_at) "
                "VALUES (:u, 'referral_joined', :t, :body, false, false, now())"
            ), {"u": user_id, "t": "🤝 Награда за приглашение друзей",
                "body": f"Задание «Пригласи друга» не засчитывало друзей — исправили и начислили {amount} монет. "
                        "Теперь оно недельное, а каждый день есть задание «Друг в игре»."})

    ids = [r[0] for r in bind.execute(sa.text(
        "SELECT id FROM task_definitions WHERE metric = 'referrals_count' AND period = 'daily' AND category = 'regular'"
    )).fetchall()]
    if ids:
        bind.execute(sa.text(
            "UPDATE user_tasks SET slot_index = NULL, period_key = NULL "
            "WHERE task_definition_id IN :ids AND slot_index IS NOT NULL AND slot_index < 100"
        ).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids})
        bind.execute(sa.text("UPDATE task_definitions SET period = 'weekly' WHERE id IN :ids")
                     .bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids})

    if bind.execute(sa.text("SELECT 1 FROM task_definitions WHERE code = :c"), {"c": CODE}).scalar() is None:
        bind.execute(sa.text(
            "INSERT INTO task_definitions (code, name, description, category, condition_type, metric, target_value, "
            "reward_coins, reward_skill_tokens, is_active, sort_order, period, points, route, is_required, created_at, updated_at) "
            "VALUES (:c, 'Друг в игре', 'Пусть приглашённый тобой друг сегодня зайдёт в игру', 'regular', 'metric_counter', "
            "'friends_active_today', 1, :r, 0, true, 0, 'daily', :p, '/friends', false, now(), now())"
        ), {"c": CODE, "r": reward, "p": points})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM task_definitions WHERE code = :c"), {"c": CODE})
    # The tasks stay weekly and the back-pay stays paid.
