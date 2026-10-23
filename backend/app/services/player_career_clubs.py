"""«Карьера игрока» clubs: the same club list as «Карьера тренера»
(CareerClub, divisions 1 = top … N, admin page «Карьера» → clubs). Each
division is a league; the coach career fills missing divisions itself
(career_league_service.ensure_catalog), and so does `prepare` here.

A club's squad: a real club (pool_club) fields its best 4-3-3 XI from the
cards with academy players a little below the club average in the gaps; a
generated club plays an academy squad around its division's base rating
(config.player_career_level_ratings) + its rating_offset. Club stars (1-5)
follow the squad rating.

Signing for a club needs both:
- rating: club rating <= player rating + config.player_career_rating_margin;
- prestige (MyPlayer.reputation): star_prestige[stars-1] + level_prestige[division-1].
The salary is level_salary[division-1] x (1 + star_salary_pct% per star
above 1) x (1 + 1% per 10 prestige, up to prestige_salary_cap%).
"""
import hashlib
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.career import CareerClub
from app.models.player import Player
from app.services import career_league_service
from app.services.career_service import division_count, division_name
from app.services.club_formation_service import get_formation_slots
from app.services.lineup_service import CATEGORY_POSITIONS, on_ideal_position

FORMATION = "4-3-3"
ACADEMY_GAP = 4
_SURNAMES = [
    "Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
    "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
    "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев",
]


def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def pick(values, index: int, default: int = 0) -> int:
    values = list(values or [])
    if not values:
        return default
    return int(values[max(0, min(len(values) - 1, index))])


def estimate_stars(rating: int) -> int:
    return 5 if rating >= 82 else 4 if rating >= 77 else 3 if rating >= 70 else 2 if rating >= 62 else 1


# --- squads ---------------------------------------------------------------------------

def _academy(club: str, slot, rating: int, n: int) -> dict:
    rng = random.Random(_seed(f"{club}:{slot.code}:{n}"))
    return {
        "slot": slot.code, "player_id": 0, "name": f"{rng.choice('АБВГДЕКМНП')}. {rng.choice(_SURNAMES)}",
        "position": slot.ideal_position.value, "rating": max(40, min(99, rating)), "academy": True,
    }


def squad_from_cards(name: str, players: list, fallback_rating: int) -> list[dict]:
    """Best XI for 4-3-3 from the cards (a club's or a nation's), academy in the gaps."""
    slots = get_formation_slots(FORMATION)
    pool = sorted(players, key=lambda p: (-p.rating, p.id))
    used: set[int] = set()
    squad: list[dict] = []
    for slot in sorted(slots, key=lambda s: 0 if s.category == "GK" else 1):
        fits = [p for p in pool if p.id not in used and p.position in CATEGORY_POSITIONS[slot.category]]
        ideal = [p for p in fits if on_ideal_position(p.position, slot.ideal_position)]
        choice = (ideal or fits or [None])[0]
        if choice is None:
            continue
        used.add(choice.id)
        squad.append({
            "slot": slot.code, "player_id": choice.id, "name": choice.display_name,
            "position": choice.position.value, "rating": choice.rating, "academy": False,
        })
    real_avg = round(sum(p["rating"] for p in squad) / len(squad)) if squad else fallback_rating
    taken = {p["slot"] for p in squad}
    for n, slot in enumerate(s for s in slots if s.code not in taken):
        squad.append(_academy(name, slot, real_avg - ACADEMY_GAP if squad else fallback_rating, n))
    order = {s.code: i for i, s in enumerate(slots)}
    return sorted(squad, key=lambda p: order[p["slot"]])


def academy_squad(name: str, rating: int) -> list[dict]:
    slots = get_formation_slots(FORMATION)
    rng = random.Random(_seed(name))
    return [_academy(name, slot, rating + rng.randint(-2, 2), i) for i, slot in enumerate(slots)]


def avg_rating(squad: list[dict]) -> int:
    return round(sum(p["rating"] for p in squad) / len(squad)) if squad else 50


# --- catalog ---------------------------------------------------------------------------

def league_out(division: int, config) -> dict:
    return {"id": division, "name": division_name(division, config), "level": division}


async def prepare(db: AsyncSession, config) -> None:
    """Fills divisions short of clubs (shared with «Карьера тренера») and
    commits. Call it before taking any row lock — never inside one."""
    await career_league_service.ensure_catalog(db, config)
    await db.commit()


async def club_catalog(db: AsyncSession, config) -> list[dict]:
    """Every active club, strongest first:
    {key, id, name, league, level, stars, rating, squad, is_demo, real_cards}."""
    count = division_count(config)
    clubs = (await db.execute(
        select(CareerClub).where(CareerClub.is_active.is_(True), CareerClub.division <= count)
    )).scalars().all()
    pool_names = [c.pool_club for c in clubs if c.pool_club]
    members: dict[str, list[Player]] = {}
    if pool_names:
        for p in (await db.execute(
            select(Player).where(Player.is_active.is_(True), Player.club.in_(pool_names))
        )).scalars().all():
            members.setdefault((p.club or "").strip(), []).append(p)
    out = []
    for club in clubs:
        base = pick(config.player_career_level_ratings, club.division - 1, 60) + (club.rating_offset or 0)
        cards = members.get(club.pool_club or "", [])
        squad = squad_from_cards(club.name, cards, base) if cards else academy_squad(club.name, base)
        rating = avg_rating(squad)
        out.append({
            "key": f"cc:{club.id}", "id": club.id, "name": club.name, "league": league_out(club.division, config),
            "level": club.division, "stars": estimate_stars(rating), "rating": rating, "squad": squad,
            "is_demo": not cards, "real_cards": len(cards),
        })
    return sorted(out, key=lambda c: (-c["rating"], c["name"]))


def find_club(clubs: list[dict], key: Optional[str]) -> Optional[dict]:
    """By key; keys saved before the shared club list ("club:<name>",
    "demo:<name>") resolve by name when a club of that name exists."""
    if not key:
        return None
    for c in clubs:
        if c["key"] == key:
            return c
    if ":" in key and not key.startswith("cc:"):
        name = key.split(":", 1)[1]
        return next((c for c in clubs if c["name"] == name), None)
    return None


# --- contract maths -------------------------------------------------------------------------

def prestige_needed(club: dict, config) -> int:
    stars = pick(config.player_career_star_prestige or [0, 30, 80, 160, 300], club["stars"] - 1)
    level = pick(config.player_career_level_prestige or [150, 80, 30, 10, 0], club["level"] - 1)
    return max(0, stars + level)


def market_salary(club: dict, prestige: int, config) -> int:
    base = pick(config.player_career_level_salary or [1500, 1000, 600, 350, 150], club["level"] - 1, 150)
    stars_pct = (club["stars"] - 1) * config.player_career_star_salary_pct
    prestige_pct = min(config.player_career_prestige_salary_cap, max(0, prestige) // 10)
    return max(0, round(base * (100 + stars_pct) / 100 * (100 + prestige_pct) / 100 / 10) * 10)


def club_access(club: dict, player_rating: int, prestige: int, config, free_agent: bool = False) -> Optional[str]:
    """None when the player may sign for the club, else why not."""
    if free_agent and club["level"] < config.player_career_free_agent_level:
        return "Без контракта — только низшие дивизионы"
    if club["rating"] > player_rating + config.player_career_rating_margin:
        return f"Нужен рейтинг {club['rating'] - config.player_career_rating_margin}+"
    need = prestige_needed(club, config)
    if prestige < need:
        return f"Нужен престиж {need}"
    return None


FILLER_NAMES = [
    "Северный Ветер", "Портовые Волки", "Динамо Рассвет", "Торпедо Восток", "Атлетик Лесной", "Горняк",
    "Спартак Заречье", "Метеор", "Звезда Юга", "Речники", "Буревестник", "Маяк", "Кристалл", "Прогресс",
]


def academy_fillers(around: dict, count: int, taken: set[str], config) -> list[dict]:
    """Invented clubs completing a division of fewer than 8 (same level,
    strength around `around`)."""
    rng = random.Random(_seed(f"fill:{around['key']}"))
    names = [n for n in FILLER_NAMES if n not in taken]
    rng.shuffle(names)
    out = []
    for i in range(count):
        name = names[i] if i < len(names) else f"Клуб {i + 1}"
        squad = academy_squad(f"fill:{name}", around["rating"] + rng.randint(-4, 4))
        out.append({
            "key": f"gen:{name}", "id": None, "name": name, "league": around["league"], "level": around["level"],
            "stars": 1, "rating": avg_rating(squad), "squad": squad, "is_demo": True, "real_cards": 0,
        })
    return out
