"""«Карьера тренера» living league: the admin-editable catalog of bot clubs
per division (built from the real clubs of the card pool, gaps filled with
generated clubs), each coach's persistent league (the same rivals across
seasons, promoted / relegated with him), head-to-head history and bot
memory, and club tenure (career-only rating for long-serving cards).

All state lives on CareerProfile.league / .tenure and the career_clubs
table; career_service calls in at season start, after every match and at
the season's end.
"""
import random
from collections import defaultdict
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.career import CareerClub, CareerProfile
from app.models.player import Player

TEAMS = 8
GENERATED_NAMES = [
    "Северный Ветер", "Портовые Волки", "Динамо Рассвет", "Торпедо Восток", "Атлетик Лесной", "Горняк",
    "Спартак Заречье", "Метеор", "Звезда Юга", "Речники", "Сокол", "Буревестник", "Химик", "Энергия",
    "Локомотив Степной", "Факел", "Авангард", "Ротор Приречье", "Шахтёр Горный", "Волна", "Кристалл", "Олимп",
    "Сатурн", "Нефтяник", "Луч", "Арсенал Озёрный", "Звезда Севера", "Прибой", "Тотем", "Маяк", "Гранит",
    "Вымпел", "Комета", "Рубин Прибрежный", "Сибиряк", "Уралец", "Балтика Новая", "Каспий", "Алмаз", "Витязь",
    "Пламя", "Северсталь", "Текстильщик", "Строитель", "Беркут", "Зенит Заречный", "Ураган", "Вега", "Орион",
    "Полёт",
]
MIN_REAL_CLUB_PLAYERS = 8


def division_count(config) -> int:
    return max(1, int(config.career_division_count or 1))


# --- catalog -------------------------------------------------------------------------------

async def build_catalog(db: AsyncSession, config, replace: bool = False) -> dict:
    """(Re)builds the bot-club catalog: real clubs of the card pool with
    enough players, ranked by their best XI and spread top-down over the
    divisions, the rest of each division's quota generated. Clubs added by
    hand (source "admin") are kept; with replace=False existing real /
    generated clubs are kept and only missing slots are filled."""
    count = division_count(config)
    quota = max(TEAMS - 1, int(config.career_division_club_count or 10))
    if replace:
        await db.execute(delete(CareerClub).where(CareerClub.source.in_(("real", "generated"))))
        await db.flush()
    existing = (await db.execute(select(CareerClub))).scalars().all()
    per_division: dict[int, int] = defaultdict(int)
    taken_names = set()
    taken_pool = set()
    for club in existing:
        per_division[club.division] += int(club.is_active)
        taken_names.add(club.name)
        if club.pool_club:
            taken_pool.add(club.pool_club)

    players = (await db.execute(select(Player).where(Player.is_active.is_(True)))).scalars().all()
    by_club: dict[str, list[int]] = defaultdict(list)
    for p in players:
        if p.club and p.club.strip():
            by_club[p.club.strip()].append(p.rating)
    real = [
        (sum(sorted(r, reverse=True)[:11]) / min(11, len(r)), name)
        for name, r in by_club.items() if len(r) >= MIN_REAL_CLUB_PLAYERS and name not in taken_pool
    ]
    real.sort(reverse=True)

    added = 0
    queue = list(real)
    for division in range(1, count + 1):
        while per_division[division] < quota and queue:
            _, name = queue.pop(0)
            db.add(CareerClub(name=name[:64], division=division, source="real", pool_club=name))
            taken_names.add(name[:64])
            per_division[division] += 1
            added += 1
    rng = random.Random(count * 31 + quota)
    names = [n for n in GENERATED_NAMES if n not in taken_names]
    rng.shuffle(names)
    serial = 1
    for division in range(1, count + 1):
        while per_division[division] < quota:
            if names:
                name = names.pop()
            else:
                name = f"ФК Дивизион {division}-{serial}"
                serial += 1
            db.add(CareerClub(name=name, division=division, source="generated"))
            per_division[division] += 1
            added += 1
    await db.flush()
    return {"added": added, "divisions": dict(per_division)}


async def ensure_catalog(db: AsyncSession, config) -> None:
    """A division without enough active clubs gets its catalog filled."""
    counts = dict((await db.execute(
        select(CareerClub.division, func.count()).where(CareerClub.is_active.is_(True)).group_by(CareerClub.division)
    )).all())
    if any(counts.get(d, 0) < TEAMS - 1 for d in range(1, division_count(config) + 1)):
        await build_catalog(db, config)


async def clubs_by_id(db: AsyncSession, ids: list[int]) -> dict[int, CareerClub]:
    if not ids:
        return {}
    rows = (await db.execute(select(CareerClub).where(CareerClub.id.in_(ids)))).scalars().all()
    return {c.id: c for c in rows}


# --- the coach's league -----------------------------------------------------------------------

async def league_clubs(db: AsyncSession, profile: CareerProfile, division: int, config, seed: int) -> list[CareerClub]:
    """The seven bot clubs of the coach's next league in `division`: the
    ones carried over from last season (still active and in the catalog),
    topped up from the division's catalog."""
    await ensure_catalog(db, config)
    league = dict(profile.league or {})
    keep_ids = [int(i) for i in league.get("next_clubs") or []] if league.get("next_division") == division else []
    kept = list((await clubs_by_id(db, keep_ids)).values())
    kept = [c for c in kept if c.is_active][: TEAMS - 1]
    pool = (await db.execute(
        select(CareerClub).where(CareerClub.division == division, CareerClub.is_active.is_(True)).order_by(CareerClub.id)
    )).scalars().all()
    rng = random.Random(seed)
    fresh = [c for c in pool if c.id not in {k.id for k in kept}]
    rng.shuffle(fresh)
    chosen = kept + fresh[: TEAMS - 1 - len(kept)]
    if len(chosen) < TEAMS - 1:  # tiny catalog: any active club
        others = (await db.execute(select(CareerClub).where(CareerClub.is_active.is_(True)))).scalars().all()
        rng.shuffle(others)
        chosen += [c for c in others if c.id not in {x.id for x in chosen}][: TEAMS - 1 - len(chosen)]
    return chosen


def plan_next_league(profile: CareerProfile, table: list[dict], teams: list[dict], current: int,
                     my_next_division: int, division_after) -> None:
    """At the season's end: the bot clubs that end up in the coach's next
    division (they stay up/down with him, or go up/down with him) are
    carried into his next league."""
    place_of = {row["team_index"]: n + 1 for n, row in enumerate(table)}
    next_clubs = []
    for team in teams:
        club_id = team.get("club_id")
        if club_id is None:
            continue
        their_next = division_after(current, place_of[team["index"]])
        if their_next == my_next_division:
            next_clubs.append(club_id)
    league = dict(profile.league or {})
    league.update(next_division=my_next_division, next_clubs=next_clubs)
    profile.league = league
    flag_modified(profile, "league")


def record_meeting(profile: CareerProfile, club_id: Optional[int], own: int, opp: int, tactic_preset: Optional[str]) -> None:
    """Head-to-head with a bot club, and its memory of tactics that beat it."""
    if club_id is None:
        return
    league = dict(profile.league or {})
    history = dict(league.get("history") or {})
    row = dict(history.get(str(club_id)) or {"w": 0, "d": 0, "l": 0})
    row["w" if own > opp else "d" if own == opp else "l"] += 1
    history[str(club_id)] = row
    league["history"] = history
    if own > opp and tactic_preset:
        memory = dict(league.get("memory") or {})
        memory[str(club_id)] = (list(memory.get(str(club_id)) or []) + [tactic_preset])[-5:]
        league["memory"] = memory
    profile.league = league
    flag_modified(profile, "league")


def head_to_head(profile: Optional[CareerProfile], club_id: Optional[int]) -> Optional[dict]:
    if profile is None or club_id is None:
        return None
    row = ((profile.league or {}).get("history") or {}).get(str(club_id))
    if not row:
        return {"w": 0, "d": 0, "l": 0, "meetings": 0}
    return {**row, "meetings": row["w"] + row["d"] + row["l"]}


def remembered_tactic(profile: Optional[CareerProfile], club_id: Optional[int]) -> Optional[str]:
    """A preset that beat this club at least twice (most recent first) —
    what a pro/legend club prepares for before seeing anything this season."""
    if profile is None or club_id is None:
        return None
    memory = list(((profile.league or {}).get("memory") or {}).get(str(club_id)) or [])
    for preset in reversed(memory):
        if memory.count(preset) >= 2:
            return preset
    return None


# --- club tenure ----------------------------------------------------------------------------

def add_tenure(profile: CareerProfile, minutes: dict[int, int]) -> None:
    tenure = dict(profile.tenure or {})
    for card_id, mins in minutes.items():
        if mins > 0 and card_id > 0:
            tenure[str(card_id)] = int(tenure.get(str(card_id), 0)) + int(mins)
    profile.tenure = tenure
    flag_modified(profile, "tenure")


def tenure_bonus(profile: Optional[CareerProfile], card_id: int, config) -> int:
    if profile is None:
        return 0
    per_point = max(1, int(config.career_tenure_minutes_per_point or 900))
    minutes = int((profile.tenure or {}).get(str(card_id), 0))
    return min(int(config.career_tenure_max or 0), minutes // per_point)
