"""«Ферги Тайм»: the game type; tasks for the new modes (metric
"played:<mode>", task_service.PLAYED_PREFIX); three more «Попробуй режим» steps
on the «Путь дебютанта».

Rewards are ordinary task_definitions / newbie_tasks values, editable in the admin.

Revision ID: 0257
Revises: 0256
Create Date: 2026-11-05
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0257"
down_revision: Union[str, None] = "0256"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# code, name, description, metric, target, coins, points, period, route
TASKS = [
    ("fergie_day", "Ферги Тайм", "Сыграй матч в «Ферги Тайм»", "played:game:fergie_time", 1, 150, 20, "daily", "/play/fergie-time"),
    ("one_on_one_day", "Выход один на один", "Сыграй 3 раза в «Атаку 1 на 1»", "played:game:one_on_one", 3, 100, 20, "daily", "/play/one-on-one"),
    ("otvetka_day", "Ответный удар", "Сыграй матч в «Ответке»", "played:game:otvetka", 1, 150, 20, "daily", "/play/otvetka"),
    ("blackjack_day", "Добавленное время", "Сыграй партию в «21»", "played:blackjack", 1, 100, 20, "daily", "/play/blackjack"),
    ("mordoboi_day", "На ринг", "Проведи бой в «Мордобое»", "played:mordoboi", 1, 100, 20, "daily", "/play/mordoboi"),
    ("kontra_day", "Контратака дня", "Проведи бой в «Контратаке»", "played:kontra", 1, 100, 20, "daily", "/play/kontra"),
    ("weekly_fergie_5", "Время Ферги", "Сыграй 5 матчей в «Ферги Тайм» за неделю", "played:game:fergie_time", 5, 700, 30, "weekly", "/play/fergie-time"),
    ("weekly_otvetka_5", "Серия ответов", "Сыграй 5 матчей в «Ответке» за неделю", "played:game:otvetka", 5, 700, 30, "weekly", "/play/otvetka"),
    ("weekly_one_on_one_15", "Мастер выхода", "Сыграй 15 раз в «Атаку 1 на 1» за неделю", "played:game:one_on_one", 15, 600, 30, "weekly", "/play/one-on-one"),
]
NEWBIE_TASKS = [
    {"code": "one_on_one", "label": "Разыграй «Атаку 1 на 1»", "mode": "game:one_on_one", "path": "/play/one-on-one", "coins": 1000},
    {"code": "otvetka", "label": "Сыграй «Ответку»", "mode": "game:otvetka", "path": "/play/otvetka", "coins": 1000},
    {"code": "fergie_time", "label": "Вырви победу в «Ферги Тайм»", "mode": "game:fergie_time", "path": "/play/fergie-time", "coins": 1000},
]


def upgrade() -> None:
    op.execute("ALTER TYPE game_type_enum ADD VALUE IF NOT EXISTS 'fergie_time'")
    bind = op.get_bind()
    existing = set(bind.execute(sa.text("SELECT code FROM task_definitions")).scalars())
    for i, (code, name, description, metric, target, coins, points, period, route) in enumerate(TASKS):
        if code in existing:
            continue
        bind.execute(sa.text(
            "INSERT INTO task_definitions (code, name, description, category, condition_type, metric, target_value, "
            "reward_coins, reward_skill_tokens, is_active, sort_order, period, points, route, is_required, created_at, updated_at) "
            "VALUES (:code, :name, :description, 'regular', 'metric_counter', :metric, :target, :coins, 0, true, :sort, "
            ":period, :points, :route, false, now(), now())"
        ), {"code": code, "name": name, "description": description, "metric": metric, "target": target,
            "coins": coins, "sort": 200 + i, "period": period, "points": points, "route": route})
    raw = bind.execute(sa.text("SELECT newbie_tasks FROM game_config WHERE id = 1")).scalar()
    if raw is not None:
        tasks = json.loads(raw) if isinstance(raw, str) else list(raw)
        have = {t.get("code") for t in tasks}
        tasks += [t for t in NEWBIE_TASKS if t["code"] not in have]
        bind.execute(
            sa.text("UPDATE game_config SET newbie_tasks = CAST(:tasks AS json) WHERE id = 1"),
            {"tasks": json.dumps(tasks, ensure_ascii=False)},
        )


def downgrade() -> None:
    # The enum value stays: Postgres can't drop one. Sessions of the type stay with it.
    bind = op.get_bind()
    op.execute("DELETE FROM task_definitions WHERE code IN (" + ", ".join(f"'{t[0]}'" for t in TASKS) + ")")
    raw = bind.execute(sa.text("SELECT newbie_tasks FROM game_config WHERE id = 1")).scalar()
    if raw is not None:
        tasks = json.loads(raw) if isinstance(raw, str) else list(raw)
        gone = {t["code"] for t in NEWBIE_TASKS}
        bind.execute(
            sa.text("UPDATE game_config SET newbie_tasks = CAST(:tasks AS json) WHERE id = 1"),
            {"tasks": json.dumps([t for t in tasks if t.get("code") not in gone], ensure_ascii=False)},
        )
