"""Every game mode at a glance, read-only: the sources of the admin analytics
(MODE_SOURCES, so a new mode shows up here by itself) plus what the dashboard
lacks — do a mode's players come back to that mode. Only totals, no player.

    docker compose -f docker-compose.prod.yml exec -T backend python - < backend/scripts/mode_stats.py

Columns: players and games for 7 / 30 days; «дней» — days a player of the last
30 days played on average; «неделя к неделе» — of the players of the week
before last, how many played in the last 7 days; «вернулись» — of those who
first played 8-37 days ago, how many played again a week or more later (the
first play is only looked for in the last 60 days, so a lower bound). A mode
that keeps one row per user has no return: «Менеджер» — scripts/manager_stats.sql.
"""
import asyncio
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.game import GameSession
from app.services.admin_analytics_service import (
    GAME_TYPE_LABELS,
    MODE_SOURCES,
    _activity,
    _as_date,
    _day_start_utc,
    _funnel,
    _modes,
    _monetization,
    _retention,
    _source_select,
    local_today,
)

HISTORY_DAYS = 60
NO_RETURN = {"Менеджер (клубы)"}


async def days_by_mode(db: AsyncSession, today: date) -> dict[str, dict[int, set[date]]]:
    """{mode label: {user: the days they played}} for the last HISTORY_DAYS."""
    since = _day_start_utc(today - timedelta(days=HISTORY_DAYS - 1))
    modes: dict[str, dict[int, set[date]]] = defaultdict(lambda: defaultdict(set))
    for src in MODE_SOURCES:
        for col in src.user_cols:
            rows = await db.execute(_source_select(src, col, since).add_columns(func.date(src.ts).label("day")).distinct())
            for uid, day in rows.all():
                modes[src.label][uid].add(_as_date(day))
    rows = await db.execute(
        select(GameSession.game_type, GameSession.user_id, func.date(GameSession.created_at))
        .where(GameSession.created_at >= since).distinct()
    )
    for game_type, uid, day in rows.all():
        value = getattr(game_type, "value", str(game_type))
        modes[GAME_TYPE_LABELS.get(value, value)][uid].add(_as_date(day))
    return modes


def returns(players: dict[int, set[date]], today: date) -> dict:
    last_week, week_before, active_days = 0, 0, []
    came_back, newcomers = 0, 0
    for days in players.values():
        ago = {(today - d).days for d in days}
        in_last = any(n < 7 for n in ago)
        if any(7 <= n < 14 for n in ago):
            week_before += 1
            last_week += in_last
        month = sum(n < 30 for n in ago)
        if month:
            active_days.append(month)
        first = max(ago)
        if 8 <= first <= 37:
            newcomers += 1
            came_back += any(n <= first - 7 for n in ago)
    return {
        "avg_days": round(sum(active_days) / len(active_days), 1) if active_days else None,
        "week_before": week_before, "last_week": last_week,
        "newcomers": newcomers, "came_back": came_back,
    }


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} {round(100 * part / whole)}%" if whole else "—"


def _print_modes(week: list[dict], month: list[dict], modes: dict, today: date) -> None:
    by_week = {r["label"]: r for r in week}
    print(f"{'режим':<28}{'игроков 7д':>11}{'30д':>7}{'игр 7д':>9}{'30д':>9}{'дней':>6}  {'неделя к неделе':<17}вернулись")
    for row in month:
        label = row["label"]
        r = returns(modes.get(label, {}), today)
        seven = by_week.get(label, {"players": 0, "games": 0})
        weekly, back = ("—", "—") if label in NO_RETURN else (_pct(r["last_week"], r["week_before"]), _pct(r["came_back"], r["newcomers"]))
        print(f"{label:<28}{seven['players']:>11}{row['players']:>7}{seven['games']:>9}{row['games']:>9}"
              f"{r['avg_days'] if r['avg_days'] is not None else '—':>6}  {weekly:<17}{back}")


async def main() -> None:
    today = local_today()
    since = {n: _day_start_utc(today - timedelta(days=n - 1)) for n in (7, 30)}
    async with AsyncSessionLocal() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        activity = await _activity(db, 30, today)
        retention = await _retention(db, 30, today)
        funnel = await _funnel(db, 30, today)
        money = await _monetization(db, 30, today, activity["active_in_period"])
        week, month = await _modes(db, since[7]), await _modes(db, since[30])
        modes = await days_by_mode(db, today)

    dau = [d["count"] for d in activity["dau_by_day"]]
    print(f"=== Игра на {today} ===")
    print(f"всего {activity['total_users']}, DAU сегодня {activity['dau_today']}, средний за 30 дней {round(sum(dau) / len(dau))}, "
          f"WAU {activity['wau']}, MAU {activity['mau']}")
    print("удержание новых:", {k: v for k, v in retention["summary"].items() if not k.endswith("eligible")})
    print("воронка новых за 30 дней:", ", ".join(f"{s['label']} {s['users']}" for s in funnel["steps"]))
    print(f"\n=== Stars за 30 дней: {money['stars_total']}, покупателей {money['payers']}, ARPPU {money['arppu']} ===")
    for p in money["by_product"]:
        print(f"{p['product']:<40}{p['stars']:>9} ⭐{p['purchases']:>7} шт.")
    print("\n=== Режимы ===")
    _print_modes(week, month, modes, today)


if __name__ == "__main__":
    asyncio.run(main())
