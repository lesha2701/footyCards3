"""Admin product analytics: activity (DAU/WAU/MAU), retention cohorts, mode
popularity, the new-player funnel and Stars monetization.

Read-only aggregates — no per-user data leaves this module. Activity history
comes from `user_daily_activity` (one row per user per local day, see
models/user_activity.py); "days" are local calendar days in
settings.timezone, the same clock the daily login streak uses.

Mode popularity and the funnel read the existing per-mode tables, so they
count games as the database records them: two-player tables (Тактико,
Стратего, Пенальти PvP) count one game per match row and every human seat
as a player; bot opponents are not players.
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import ColumnElement, distinct, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.blackjack import BlackjackMatch
from app.models.career import CareerParticipant
from app.models.game import GameSession
from app.models.magnate import MagnateSeat
from app.models.match import Match
from app.models.pack import PackOpening, StarsInvoice
from app.models.penalty import PenaltyMatch
from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant
from app.models.stratego import StrategoMatch
from app.models.tactico import TacticoMatch
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.models.wheel import WheelSpin

RETENTION_DAYS = (1, 7, 30)

GAME_TYPE_LABELS: dict[str, str] = {
    "memory_sequence": "Memory Sequence",
    "card_arena": "Card Arena (сессии)",
    "saboteur": "Сапёр",
    "penalty": "Пенальти",
    "free_kick": "Штрафной удар",
    "football_hangman": "Футбольные буквы",
    "card_pairs": "Пары",
    "fut_draft": "FUT Draft",
    "club_sequence": "Клубные мини-игры",
    "club_missing_item": "Клубные мини-игры",
    "club_penalty": "Клубные мини-игры",
    "club_position_match": "Клубные мини-игры",
    "position_match": "Клубные мини-игры",
}


@dataclass(frozen=True)
class _Source:
    """One table that records a game: its timestamp, the human user columns
    (each row is one game), and an optional join for tables that keep the
    timestamp on a parent row."""

    key: str
    label: str
    model: Any
    ts: Any
    user_cols: tuple[Any, ...]
    join: Optional[tuple[Any, Any]] = None
    game_key: Optional[Any] = None  # what identifies one game (default: the row)


MODE_SOURCES: tuple[_Source, ...] = (
    # Arena's opponent_user_id is the player whose name/lineup the bot
    # borrowed — they didn't play, so only the challenger counts.
    _Source("arena", "Card Arena", Match, Match.created_at, (Match.user_id,)),
    _Source(
        "tactico", "Тактико", TacticoMatch, TacticoMatch.created_at,
        (TacticoMatch.user_id, TacticoMatch.opponent_user_id),
    ),
    _Source(
        "stratego", "Стратего", StrategoMatch, StrategoMatch.created_at,
        (StrategoMatch.user_id, StrategoMatch.opponent_user_id),
    ),
    _Source(
        "penalty_pvp", "Пенальти PvP", PenaltyMatch, PenaltyMatch.created_at,
        (PenaltyMatch.user_id, PenaltyMatch.opponent_user_id),
    ),
    _Source("blackjack", "21: Добавленное время", BlackjackMatch, BlackjackMatch.created_at, (BlackjackMatch.user_id,)),
    _Source(
        "magnate", "Футбольный магнат", MagnateSeat, MagnateSeat.joined_at, (MagnateSeat.user_id,),
        game_key=MagnateSeat.match_id,
    ),
    _Source(
        "player_tournament", "Турниры игроков", PlayerTournamentParticipant, PlayerTournament.created_at,
        (PlayerTournamentParticipant.user_id,),
        join=(PlayerTournament, PlayerTournament.id == PlayerTournamentParticipant.tournament_id),
        game_key=PlayerTournamentParticipant.tournament_id,
    ),
    _Source("career", "Карьера тренера (сезоны)", CareerParticipant, CareerParticipant.created_at, (CareerParticipant.user_id,)),
    _Source("wheel", "Колесо фортуны", WheelSpin, WheelSpin.created_at, (WheelSpin.user_id,)),
)


def _local_day(dt: datetime) -> date:
    return ensure_aware(dt).astimezone(app_timezone()).date()


def _day_start_utc(day: date) -> datetime:
    """UTC instant at which local `day` begins."""
    return datetime.combine(day, datetime.min.time(), tzinfo=app_timezone()).astimezone(timezone.utc)


def _window(days: int, today: date) -> tuple[date, datetime]:
    first_day = today - timedelta(days=days - 1)
    return first_day, _day_start_utc(first_day)


def _filled(first_day: date, today: date, counts: dict[date, int]) -> list[dict]:
    n = (today - first_day).days + 1
    return [{"date": (first_day + timedelta(days=i)).isoformat(), "count": int(counts.get(first_day + timedelta(days=i), 0))} for i in range(n)]


def _as_date(value: Any) -> date:
    # SQLite hands Date columns back as strings in some aggregate paths.
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _source_select(src: _Source, uid: Any, since: datetime, where: Optional[ColumnElement] = None):
    q = select(uid.label("uid"))
    q = q.select_from(src.model)
    if src.join is not None:
        q = q.join(*src.join)
    q = q.where(src.ts >= since, uid.is_not(None))
    if where is not None:
        q = q.where(where)
    return q


# --- Activity ------------------------------------------------------------------


async def _activity(db: AsyncSession, days: int, today: date) -> dict:
    first_day, since = _window(days, today)
    dau_rows = (await db.execute(
        select(UserDailyActivity.day, func.count())
        .where(UserDailyActivity.day >= first_day, UserDailyActivity.day <= today)
        .group_by(UserDailyActivity.day)
    )).all()
    dau = {_as_date(d): c for d, c in dau_rows}

    async def distinct_since(n: int) -> int:
        return int((await db.execute(
            select(func.count(distinct(UserDailyActivity.user_id)))
            .where(UserDailyActivity.day > today - timedelta(days=n), UserDailyActivity.day <= today)
        )).scalar_one())

    wau, mau = await distinct_since(7), await distinct_since(30)
    active_in_window = int((await db.execute(
        select(func.count(distinct(UserDailyActivity.user_id)))
        .where(UserDailyActivity.day >= first_day, UserDailyActivity.day <= today)
    )).scalar_one())

    reg_rows = (await db.execute(select(User.created_at).where(User.created_at >= since))).scalars().all()
    regs: dict[date, int] = defaultdict(int)
    for created in reg_rows:
        regs[_local_day(created)] += 1

    dau_today = int(dau.get(today, 0))
    return {
        "dau_today": dau_today,
        "wau": wau,
        "mau": mau,
        "stickiness": round(dau_today / mau, 3) if mau else None,
        "active_in_period": active_in_window,
        "dau_by_day": _filled(first_day, today, dau),
        "registrations_by_day": _filled(first_day, today, regs),
        "total_users": int((await db.execute(select(func.count(User.id)))).scalar_one()),
    }


# --- Retention -------------------------------------------------------------------


async def _retention(db: AsyncSession, days: int, today: date) -> dict:
    """Cohorts by local registration day over the window; a user is
    retained on day N if they were active exactly N days after registering.
    A cohort's DN is None until day N has been reached."""
    first_day, since = _window(days, today)
    users = (await db.execute(select(User.id, User.created_at).where(User.created_at >= since))).all()
    reg_day = {uid: _local_day(created) for uid, created in users}
    cohort_ids = list(reg_day)

    active: set[tuple[int, date]] = set()
    if cohort_ids:
        user_subq = select(User.id).where(User.created_at >= since)
        rows = (await db.execute(
            select(UserDailyActivity.user_id, UserDailyActivity.day)
            .where(UserDailyActivity.user_id.in_(user_subq), UserDailyActivity.day > first_day)
        )).all()
        active = {(uid, _as_date(d)) for uid, d in rows}

    by_day: dict[date, list[int]] = defaultdict(list)
    for uid, d in reg_day.items():
        by_day[d].append(uid)

    cohorts = []
    totals = {n: [0, 0] for n in RETENTION_DAYS}  # n -> [retained, eligible]
    for d in sorted(by_day):
        members = by_day[d]
        row: dict[str, Any] = {"date": d.isoformat(), "size": len(members)}
        for n in RETENTION_DAYS:
            target = d + timedelta(days=n)
            if target > today:
                row[f"d{n}"] = None
                continue
            retained = sum(1 for uid in members if (uid, target) in active)
            row[f"d{n}"] = round(retained / len(members), 3)
            totals[n][0] += retained
            totals[n][1] += len(members)
        cohorts.append(row)

    summary = {f"d{n}": (round(r / e, 3) if e else None) for n, (r, e) in totals.items()}
    summary.update({f"d{n}_eligible": e for n, (_r, e) in totals.items()})
    return {"cohorts": cohorts, "summary": summary}


# --- Modes -------------------------------------------------------------------------


async def _modes(db: AsyncSession, since: datetime) -> list[dict]:
    rows: list[dict] = []
    for src in MODE_SOURCES:
        game_col = src.game_key if src.game_key is not None else None
        games_q = select(func.count(distinct(game_col)) if game_col is not None else func.count()).select_from(src.model)
        if src.join is not None:
            games_q = games_q.join(*src.join)
        games = int((await db.execute(games_q.where(src.ts >= since))).scalar_one())
        players_sub = union_all(*[_source_select(src, col, since) for col in src.user_cols]).subquery()
        players = int((await db.execute(select(func.count(distinct(players_sub.c.uid))))).scalar_one())
        rows.append({"key": src.key, "label": src.label, "games": games, "players": players})

    # Solo mini-games share one table, split by game type; several club
    # game types share one label, so players are de-duplicated per label.
    by_label: dict[str, dict] = {}
    players_by_label: dict[str, set] = defaultdict(set)
    type_rows = (await db.execute(
        select(GameSession.game_type, func.count())
        .where(GameSession.created_at >= since)
        .group_by(GameSession.game_type)
    )).all()
    for gt, games in type_rows:
        value = getattr(gt, "value", str(gt))
        label = GAME_TYPE_LABELS.get(value, value)
        entry = by_label.setdefault(label, {"key": f"game:{value}", "label": label, "games": 0, "players": 0})
        entry["games"] += int(games)
    user_rows = (await db.execute(
        select(GameSession.game_type, GameSession.user_id).where(GameSession.created_at >= since).distinct()
    )).all()
    for gt, uid in user_rows:
        value = getattr(gt, "value", str(gt))
        players_by_label[GAME_TYPE_LABELS.get(value, value)].add(uid)
    for label, entry in by_label.items():
        entry["players"] = len(players_by_label[label])
    rows.extend(by_label.values())

    return sorted(rows, key=lambda r: (-r["players"], -r["games"], r["label"]))


# --- Funnel ------------------------------------------------------------------------


async def _users_in(db: AsyncSession, q) -> set[int]:
    return {uid for (uid,) in (await db.execute(q)) if uid is not None}


async def _funnel(db: AsyncSession, days: int, today: date) -> dict:
    """New players registered in the window, and how many of them reached
    each step at any point since registering."""
    first_day, since = _window(days, today)
    users = (await db.execute(select(User.id, User.created_at).where(User.created_at >= since))).all()
    cohort = {uid for uid, _ in users}
    reg_day = {uid: _local_day(created) for uid, created in users}
    cohort_q = select(User.id).where(User.created_at >= since)

    opened_pack = await _users_in(db, select(PackOpening.user_id).where(PackOpening.user_id.in_(cohort_q)).distinct())
    played = set()
    for src in MODE_SOURCES:
        for col in src.user_cols:
            q = select(col).select_from(src.model)
            if src.join is not None:
                q = q.join(*src.join)
            played |= await _users_in(db, q.where(col.in_(cohort_q)).distinct())
    played |= await _users_in(db, select(GameSession.user_id).where(GameSession.user_id.in_(cohort_q)).distinct())

    activity_rows = (await db.execute(
        select(UserDailyActivity.user_id, UserDailyActivity.day).where(UserDailyActivity.user_id.in_(cohort_q))
    )).all()
    returned = {uid for uid, d in activity_rows if _as_date(d) > reg_day.get(uid, date.max)}
    paid = await _users_in(db, select(StarsInvoice.user_id).where(
        StarsInvoice.user_id.in_(cohort_q), StarsInvoice.completed_at.is_not(None)
    ).distinct())

    total = len(cohort)
    steps = [
        ("registered", "Зарегистрировались", cohort),
        ("opened_pack", "Открыли пак", opened_pack & cohort),
        ("played", "Сыграли матч или мини-игру", played & cohort),
        ("returned", "Вернулись в другой день", returned & cohort),
        ("paid", "Купили за Stars", paid & cohort),
    ]
    return {
        "cohort_size": total,
        "steps": [
            {"key": k, "label": label, "users": len(s), "share": round(len(s) / total, 3) if total else None}
            for k, label, s in steps
        ],
    }


# --- Monetization ------------------------------------------------------------------


def _product(inv: StarsInvoice) -> str:
    if inv.pack_id is not None:
        return "Паки"
    if inv.coins_amount is not None:
        return "Монеты"
    if inv.gift_set_id is not None:
        return "Подарки"
    if inv.is_wheel_spin:
        return "Колесо фортуны"
    if inv.my_player_purchase:
        return "Мой игрок"
    if inv.is_blackjack_entry:
        return "21: Добавленное время"
    if inv.path_user_card_id is not None:
        return "Академия: попытки"
    if inv.academy_speedup:
        return "Академия: ускорение"
    return "Другое"


async def _monetization(db: AsyncSession, days: int, today: date, active_in_period: int) -> dict:
    first_day, since = _window(days, today)
    invoices = (await db.execute(
        select(StarsInvoice).where(StarsInvoice.completed_at.is_not(None), StarsInvoice.completed_at >= since)
    )).scalars().all()

    by_day: dict[date, int] = defaultdict(int)
    by_product: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    payers: set[int] = set()
    for inv in invoices:
        by_day[_local_day(inv.completed_at)] += inv.stars_amount
        p = by_product[_product(inv)]
        p[0] += inv.stars_amount
        p[1] += 1
        payers.add(inv.user_id)

    total = sum(inv.stars_amount for inv in invoices)
    return {
        "stars_total": total,
        "purchases": len(invoices),
        "payers": len(payers),
        "paying_share": round(len(payers) / active_in_period, 3) if active_in_period else None,
        "arppu": round(total / len(payers), 1) if payers else None,
        "stars_by_day": _filled(first_day, today, by_day),
        "by_product": sorted(
            ({"product": k, "stars": v[0], "purchases": v[1]} for k, v in by_product.items()),
            key=lambda r: -r["stars"],
        ),
    }


async def analytics_report(db: AsyncSession, days: int, today: Optional[date] = None) -> dict:
    today = today or local_today()
    _first, since = _window(days, today)
    activity = await _activity(db, days, today)
    return {
        "days": days,
        "today": today.isoformat(),
        "activity": activity,
        "retention": await _retention(db, days, today),
        "modes": await _modes(db, since),
        "funnel": await _funnel(db, days, today),
        "monetization": await _monetization(db, days, today, activity["active_in_period"]),
    }
