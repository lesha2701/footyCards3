"""Do the modes get played for themselves or for the tasks? Read-only.

    docker compose -f docker-compose.prod.yml exec -T backend python - < backend/scripts/task_pull.py

1. What points players at a mode: the active task definitions, the bingo pool
   and the «Путь дебютанта» tasks.
2. Bingo (cards keep their history): over the last bingo weeks, of the players
   who were active that week, how many played the mode when their card had a
   cell for it vs when it hadn't.
3. Daily tasks: a user's task row is reused for every new day, so only today
   is known. Of today's active players, how many played the mode with a task
   for it today vs without (run it in the evening, the day must have happened).
Only totals, no player.
"""
import asyncio
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select, text

from app.core.timeutil import app_timezone, ensure_aware
from app.database import AsyncSessionLocal
from app.models.bingo import BingoCard, BingoWeek
from app.models.game import GameSession
from app.models.task import TaskDefinition, UserTask
from app.models.user_activity import UserDailyActivity
from app.services import bingo_service
from app.services.admin_analytics_service import GAME_TYPE_LABELS, MODE_SOURCES, _day_start_utc, _source_select, local_today
from app.services.game_config_service import get_config

HISTORY_DAYS = 35
LABEL_BY_KEY = {s.key: s.label for s in MODE_SOURCES}
# Older task metrics / conditions that count one mode's games.
LEGACY = {
    "arena_clean_sheet_wins": "arena", "match_min_rating": "arena", "match_same_country": "arena",
    "memory_levels_completed": "game:memory_sequence", "saboteur_levels_cleared": "game:saboteur",
    "penalty_win_max_rating": "game:penalty",
}


def mode_of(metric: str | None) -> str | None:
    """A task / bingo metric → the mode label of the analytics, else None."""
    if not metric:
        return None
    metric = LEGACY.get(metric, metric)
    if metric.startswith("played:"):
        metric = metric[len("played:"):]
    if metric.startswith("game:"):
        value = metric[len("game:"):]
        return GAME_TYPE_LABELS.get(value, value)
    return LABEL_BY_KEY.get(metric)


def local_day(ts) -> date:
    return ensure_aware(ts).astimezone(app_timezone()).date()


async def plays(db, since) -> dict[str, dict[int, set[date]]]:
    """{mode label: {user: local days played}}."""
    out: dict[str, dict[int, set[date]]] = defaultdict(lambda: defaultdict(set))
    for src in MODE_SOURCES:
        for col in src.user_cols:
            for uid, ts in (await db.execute(_source_select(src, col, since).add_columns(src.ts))).all():
                out[src.label][uid].add(local_day(ts))
    rows = await db.execute(select(GameSession.game_type, GameSession.user_id, GameSession.created_at).where(GameSession.created_at >= since))
    for game_type, uid, ts in rows.all():
        value = getattr(game_type, "value", str(game_type))
        out[GAME_TYPE_LABELS.get(value, value)][uid].add(local_day(ts))
    return out


def pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole):>3}% ({part}/{whole})" if whole else "—"


async def main() -> None:
    today = local_today()
    since = _day_start_utc(today - timedelta(days=HISTORY_DAYS - 1))
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        config = await get_config(db)
        defs = (await db.execute(select(TaskDefinition).order_by(TaskDefinition.period, TaskDefinition.sort_order))).scalars().all()
        played = await plays(db, since)
        active = defaultdict(set)  # day -> users
        for uid, day in (await db.execute(select(UserDailyActivity.user_id, UserDailyActivity.day).where(UserDailyActivity.day >= today - timedelta(days=HISTORY_DAYS)))).all():
            active[day if isinstance(day, date) else date.fromisoformat(str(day))].add(uid)
        weeks = (await db.execute(select(BingoWeek).where(BingoWeek.ends_at >= since).order_by(BingoWeek.week_number))).scalars().all()
        cards = (await db.execute(select(BingoCard.week_id, BingoCard.user_id, BingoCard.cells).where(BingoCard.week_id.in_([w.id for w in weeks] or [-1])))).all()
        today_tasks = (await db.execute(
            select(UserTask.user_id, UserTask.task_definition_id, UserTask.completed_at).where(UserTask.period_key == today.isoformat())
        )).all()

    # ---- 1. what points at a mode ------------------------------------------
    print(f"=== Задания (активные), на {today} ===")
    def_mode = {}
    for d in defs:
        m = mode_of(d.metric) or mode_of(d.condition_type.value)
        def_mode[d.id] = m
        if d.is_active:
            print(f"{d.period:<7} {d.name[:44]:<45} {d.metric or d.condition_type.value:<28} цель {d.target_value:<3} → {m or '—'}")
    print("\n=== Бинго: пул ===", "(из админки)" if config.bingo_pool else "(по умолчанию)")
    pool = config.bingo_pool or bingo_service.DEFAULT_POOL
    for c in pool:
        print(f"  {c.get('label', ''):<32} {c.get('metric'):<26} → {mode_of(c.get('metric')) or '—'}")
    print("\n=== Путь дебютанта: задания ===")
    for t in config.newbie_tasks or []:
        print(f"  {t.get('label', ''):<45} → {mode_of(t.get('mode')) or t.get('mode')}")

    # ---- 2. bingo --------------------------------------------------------------
    print(f"\n=== Бинго: играли режим за неделю — с клеткой / без клетки (недель: {len(weeks)}) ===")
    week_days = {w.id: {local_day(w.starts_at) + timedelta(days=i) for i in range(7)} for w in weeks}
    with_cell, without = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    modes_in_pool = {mode_of(c.get("metric")) for c in pool} - {None}
    for week_id, uid, cells in cards:
        days = week_days.get(week_id, set())
        if not any(uid in active.get(d, ()) for d in days):
            continue
        card_modes = {mode_of(c.get("metric")) for c in cells or []}
        for m in modes_in_pool:
            hit = bool(played.get(m, {}).get(uid, set()) & days)
            bucket = with_cell if m in card_modes else without
            bucket[m][0] += hit
            bucket[m][1] += 1
    print(f"{'режим':<28}{'с клеткой':>20}{'без клетки':>22}")
    for m in sorted(modes_in_pool, key=lambda m: -with_cell[m][1]):
        print(f"{m:<28}{pct(*with_cell[m]):>20}{pct(*without[m]):>22}")

    # ---- 3. daily tasks, today ----------------------------------------------
    active_today = active.get(today, set())
    print(f"\n=== Задания дня: играли режим сегодня — с заданием / без (активных сегодня: {len(active_today)}) ===")
    task_users, done = defaultdict(set), defaultdict(int)
    for uid, def_id, completed_at in today_tasks:
        m = def_mode.get(def_id)
        if m:
            task_users[m].add(uid)
            done[m] += completed_at is not None
    print(f"{'режим':<28}{'с заданием':>20}{'без задания':>22}{'выполнили':>11}")
    for m in sorted(task_users, key=lambda m: -len(task_users[m])):
        players_today = {u for u, days in played.get(m, {}).items() if today in days}
        have = task_users[m] & active_today
        rest = active_today - task_users[m]
        print(f"{m:<28}{pct(len(have & players_today), len(have)):>20}{pct(len(rest & players_today), len(rest)):>22}{done[m]:>11}")


if __name__ == "__main__":
    asyncio.run(main())
