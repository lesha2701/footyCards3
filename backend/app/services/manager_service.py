"""«Менеджер»: every user may run his own club.

Squad (4-3-3; the owner's own «Мой игрок» and his «Академия» card always
start, the best of the rest fill the XI, others sit on the bench):
- the owner's «Мой игрок» (free; not while under contract at another club);
- one card of the owner's «Академия» (a path card, `academy_card_id`);
- up to config.manager_max_live other users' «Мои игроки» on contracts for
  1-3 seasons: a free agent is signed, a player of another club is bought
  (transfer) or borrowed for a season (loan) — the player always consents,
  and the selling club too;
- footballers of the game catalog (manager_npc), bought for 1-3 seasons or
  loaned for one; a footballer plays for one club at a time.

Money: club euros (`ManagerClub.budget`), never converted to coins. A season
grant from the division (config.manager_division_budget) plus a «Клубная
база» bonus (per base level, «Отдел маркетинга» sponsors, «Клубный магазин»
merchandise — capped at config.manager_base_bonus_cap_pct of the grant),
match income and home ticket sales («Стадион» level, «Клубный отель» /
ticket prices %), prizes, fans' merchandise (manager_shop). Transfer fees go
budget to budget. Catalog wages are a sink (scaled by division, cut by
«Бухгалтерия»); users' players get coins per season (capped), the club pays
their euro equivalent. Values follow the Transfermarkt-like curve
config.manager_value_ratings / manager_value_eur.

Pyramid: divisions 1..N (config.manager_divisions), division d holds
league_size × 2^(d-1) clubs in leagues of config.manager_league_size (the
lowest one has no limit); every new club starts in the lowest division and
climbs one division a season at most. Season = one ISO week (key "2026-W43"): preseason
(transfer window) from Monday 00:00 for config.manager_preseason_hours; then
`ensure_season` (once per key) ends expired contracts, pays the grant and
wages, loans footballers into empty XI slots, freezes the XIs and draws each
division into leagues by strength (bots near the league's average fill
them); league_size − 1 rounds at config.manager_slots. When every league
has finished, `_settle` moves clubs one division at most: with a full
division above, config.manager_promote clubs per league go up and twice as
many per league come down (the pyramid stays ×2); while the division above
has room (at the start the upper divisions are empty), the best of each
league (up to its top half) fill it — climbing is quicker early on. Promoted clubs get a
bonus, relegated ones a parachute. A club whose league runs can't trade.

No scheduler of its own: the season start and the rounds run lazily on
reads and from the bot's manager sweep (`resolve_all_due`). The owners get
one evening digest a day, not a notification per match.
"""
import copy
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.card import UserCard
from app.models.card_path import UserAcademy
from app.models.club_base import UserClubBase
from app.models.enums import NotificationType, Position, Rarity, TransactionType
from app.models.manager_club import (
    ManagerClub,
    ManagerContract,
    ManagerLeague,
    ManagerNpc,
    ManagerSeason,
    ManagerValueHistory,
)
from app.models.my_player import MyPlayer
from app.models.player import Player
from app.models.user import User
from app.services import club_base_service, my_player_service, player_career_clubs as pcc, tournament_match_engine
from app.services import manager_tactics as tactics, trade_guard_service, wallet_service
from app.services.manager_tactics import DEFAULT_FORMATION
from app.services.career_service import standings
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, on_ideal_position
from app.services.notification_service import notify
from app.services.player_tournament_simulation_service import _EngineCard, _engine_card

CONTRACT_SEASONS = (1, 2, 3)
LINES = ("GK", "DEF", "MID", "FWD")
NAME_MIN, NAME_MAX = 3, 32
FIRST_ROUND_LEAD = timedelta(hours=1)
FILLER_GAP = 8  # academy kids play this far below the division rating
AUTO_RANGE = 4  # automatic signings: division rating ± this
RELATED = "manager_club"
DEFAULT_SLOTS = ((13, 0), (17, 0), (21, 0))


def _name(user: Optional[User]) -> str:
    return (user.first_name or user.username or "Игрок") if user else "Игрок"


def _level(user: User, config) -> int:
    return my_player_service.level_info(user.my_player_xp or 0, config)[0]


def _category(position: Position) -> str:
    return next(cat for cat, positions in CATEGORY_POSITIONS.items() if position in positions)


def _pick(values, index: int, default: int = 0) -> int:
    values = list(values or [])
    return int(values[max(0, min(len(values) - 1, index))]) if values else default


def division_name(division: int) -> str:
    return f"Дивизион {division}"


def league_size(config) -> int:
    size = max(4, int(config.manager_league_size or 16))
    return size - size % 2


def rounds_of(config) -> int:
    return league_size(config) - 1


def _pct(values, division: int) -> int:
    return _pick(values, division - 1, 100)


async def _users(db: AsyncSession, ids) -> dict[int, User]:
    ids = set(ids)
    if not ids:
        return {}
    return {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}


async def _my_players(db: AsyncSession, ids) -> dict[int, MyPlayer]:
    ids = set(ids)
    if not ids:
        return {}
    return {mp.user_id: mp for mp in (await db.execute(select(MyPlayer).where(MyPlayer.user_id.in_(ids)))).scalars().all()}


def _enabled(config) -> None:
    if not config.manager_enabled:
        raise ConflictError("Режим «Менеджер» сейчас выключен")


# --- calendar ------------------------------------------------------------------------

def slots_of(config) -> list[tuple[int, int]]:
    out = []
    for raw in config.manager_slots or []:
        try:
            hour, minute = (int(x) for x in str(raw).split(":", 1))
        except ValueError:
            continue
        if 0 <= hour < 24 and 0 <= minute < 60:
            out.append((hour, minute))
    return sorted(set(out)) or list(DEFAULT_SLOTS)


def week_start(now: datetime) -> datetime:
    """Monday 00:00 (local) of `now`'s week, as an aware datetime."""
    local = ensure_aware(now).astimezone(app_timezone())
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, time(0, 0), tzinfo=app_timezone())


def season_key(now: datetime) -> str:
    year, week, _ = week_start(now).date().isocalendar()
    return f"{year}-W{week:02d}"


def preseason_end(now: datetime, config) -> datetime:
    return week_start(now) + timedelta(hours=config.manager_preseason_hours)


def season_schedule(start: datetime, config) -> list[str]:
    """The season's rounds at the manager slots, the first at least
    FIRST_ROUND_LEAD after `start`."""
    tz = app_timezone()
    earliest = ensure_aware(start).astimezone(tz) + FIRST_ROUND_LEAD
    day: date = earliest.date()
    out: list[datetime] = []
    total = rounds_of(config)
    while len(out) < total:
        for hour, minute in slots_of(config):
            at = datetime.combine(day, time(hour, minute), tzinfo=tz)
            if at >= earliest and len(out) < total:
                out.append(at)
        day += timedelta(days=1)
    return [t.astimezone(timezone.utc).isoformat() for t in out]


def circle_round_robin(teams: int) -> list[list[list[int]]]:
    """Single round robin (circle method), home/away alternating."""
    order = list(range(teams))
    rounds = []
    for r in range(teams - 1):
        pairs = []
        for i in range(teams // 2):
            a, b = order[i], order[teams - 1 - i]
            pairs.append([a, b] if (r + i) % 2 == 0 else [b, a])
        rounds.append(pairs)
        order = [order[0], order[-1], *order[1:-1]]
    return rounds


# --- money ---------------------------------------------------------------------------

def _nice(amount: float) -> int:
    """Two significant digits: 3 456 789 → 3 500 000."""
    if amount <= 0:
        return 0
    step = 10 ** max(0, int(math.floor(math.log10(amount))) - 1)
    return int(round(amount / step) * step)


def value_of(rating: int, config) -> int:
    """Transfer value (club euros) of a footballer of this rating: log-linear
    between the configured points (Transfermarkt-like), flat beyond them."""
    points = sorted(zip(list(config.manager_value_ratings or []), list(config.manager_value_eur or [])))
    points = [(int(r), max(1, int(v))) for r, v in points]
    if not points:
        return 100_000
    if rating <= points[0][0]:
        return _nice(points[0][1])
    if rating >= points[-1][0]:
        return _nice(points[-1][1])
    for (r1, v1), (r2, v2) in zip(points, points[1:]):
        if r1 <= rating <= r2:
            share = (rating - r1) / (r2 - r1) if r2 != r1 else 0
            return _nice(math.exp(math.log(v1) + (math.log(v2) - math.log(v1)) * share))
    return _nice(points[-1][1])


def npc_terms(rating: int, config, division: Optional[int] = None, discount_pct: int = 0) -> dict:
    """value, the base wage per season, the wage this club pays in its
    division, the season loan fee and the sell-back price."""
    value = value_of(rating, config)
    wage = value * config.manager_wage_pct // 100
    pay = wage * (_pct(config.manager_division_wage_pct, division) if division else 100) // 100
    pay = pay * (100 - max(0, min(90, discount_pct))) // 100
    return {
        "value": value, "wage": wage, "wage_now": pay,
        "loan_fee": _nice(value * config.manager_loan_fee_pct / 100), "sell_back": _nice(value * config.manager_sell_back_pct / 100),
    }


def live_value(rating: int, contract: Optional[ManagerContract], config) -> int:
    """A user's player: the value of his rating plus form at his club."""
    involvement = (contract.goals + contract.assists) if contract else 0
    form = min(config.manager_form_bonus_cap, config.manager_form_bonus_pct * involvement)
    return _nice(value_of(rating, config) * (100 + form) / 100)


def wage_eur(coins: int, config) -> int:
    return max(0, coins) * config.manager_wage_eur_per_coin


async def base_snapshot(db: AsyncSession, owner_id: int, config) -> dict:
    """What the owner's «Клубная база» gives the club: building levels that
    matter and the (capped) effects."""
    base = await db.get(UserClubBase, owner_id)
    levels = club_base_service.effective_levels(base)
    effects = club_base_service.effects_from_levels(levels, config)
    academy = (await db.execute(select(UserAcademy.total_level).where(UserAcademy.user_id == owner_id))).scalar_one_or_none() or 0
    return {
        "level": sum(int(v) for v in levels.values()) + int(academy),
        "stadium": int(levels.get("stadium", 0)), "marketing": int(levels.get("marketing", 0)), "shop": int(levels.get("shop", 0)),
        "matchday_pct": int(effects.get("matchday_pct", 0)), "discount_pct": int(effects.get("discount_pct", 0)),
        "capacity": club_base_service.value_at(config, "stadium", "capacity", int(levels.get("stadium", 0)))
        if levels.get("stadium") else 0,
    }


def season_grant(division: int, snap: dict, config) -> dict:
    grant = _pick(config.manager_division_budget, division - 1, 2_000_000)
    raw = config.manager_budget_per_base_level * snap["level"] + config.manager_sponsor_eur_per_level * snap["marketing"] \
        + config.manager_merch_eur_per_level * snap["shop"]
    bonus = min(raw, grant * config.manager_base_bonus_cap_pct // 100)
    return {"grant": grant, "bonus": bonus, "bonus_raw": raw, "total": grant + bonus}


def ticket_income(division: int, snap: dict, config) -> int:
    per_match = config.manager_ticket_eur_per_level * snap.get("stadium", 0) * _pct(config.manager_division_income_pct, division) // 100
    return per_match * (100 + snap.get("matchday_pct", 0)) // 100


async def _grant_budget(db: AsyncSession, club: ManagerClub, key: str, config) -> int:
    """The season grant, once per season key (the club row is locked)."""
    if club.budget_season == key:
        return 0
    amount = season_grant(club.division, await base_snapshot(db, club.owner_id, config), config)["total"]
    club.budget += amount
    club.budget_season = key
    return amount


# --- pyramid -----------------------------------------------------------------------------

def capacity(division: int, config) -> int:
    return league_size(config) * 2 ** (division - 1)


def depth_of(config) -> int:
    return max(1, int(config.manager_divisions or 1))


def entry_division(config) -> int:
    """Every new club starts at the bottom of the pyramid."""
    return depth_of(config)


# --- clubs -----------------------------------------------------------------------------

async def _owned_club(db: AsyncSession, owner_id: int, lock: bool = False) -> Optional[ManagerClub]:
    stmt = select(ManagerClub).where(ManagerClub.owner_id == owner_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _lock_clubs(db: AsyncSession, ids) -> dict[int, ManagerClub]:
    """Row-locks clubs in id order (the lock order everywhere: clubs, then users)."""
    out = {}
    for club_id in sorted(set(i for i in ids if i)):
        club = (await db.execute(
            select(ManagerClub).where(ManagerClub.id == club_id).with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if club is None:
            raise NotFoundError("Клуб не найден")
        out[club_id] = club
    return out


async def is_playing(db: AsyncSession, club: ManagerClub) -> bool:
    if not club.league_id:
        return False
    status = (await db.execute(select(ManagerLeague.status).where(ManagerLeague.id == club.league_id))).scalar_one_or_none()
    return status == "active"


async def _ensure_window(db: AsyncSession, club: ManagerClub, whose: str = "Твой клуб") -> None:
    if await is_playing(db, club):
        raise ConflictError(f"{whose} играет сезон — трансферы откроются в предсезонку")


async def _active_contract(db: AsyncSession, user_id: int) -> Optional[ManagerContract]:
    """The club the player plays for now (a loan contract while on loan)."""
    return (await db.execute(
        select(ManagerContract).where(ManagerContract.user_id == user_id, ManagerContract.status == "active").limit(1)
    )).scalar_one_or_none()


async def _contracts(db: AsyncSession, club_id: int, statuses: tuple[str, ...] = ("active",)) -> list[ManagerContract]:
    return list((await db.execute(
        select(ManagerContract).where(ManagerContract.club_id == club_id, ManagerContract.status.in_(statuses))
        .order_by(ManagerContract.id)
    )).scalars().all())


async def _npcs(db: AsyncSession, club_id: int) -> list[ManagerNpc]:
    return list((await db.execute(
        select(ManagerNpc).where(ManagerNpc.club_id == club_id, ManagerNpc.status == "active").order_by(ManagerNpc.id)
    )).scalars().all())


async def _academy_card(db: AsyncSession, club: ManagerClub) -> Optional[UserCard]:
    if not club.academy_card_id:
        return None
    card = (await db.execute(
        select(UserCard).options(selectinload(UserCard.player)).where(UserCard.id == club.academy_card_id)
    )).scalar_one_or_none()
    if card is None or card.owner_id != club.owner_id or card.player is None or card.player.path_talent_code is None:
        return None
    return card


async def academy_options(db: AsyncSession, owner_id: int) -> list[UserCard]:
    return list((await db.execute(
        select(UserCard).join(Player, Player.id == UserCard.player_id).options(selectinload(UserCard.player))
        .where(UserCard.owner_id == owner_id, Player.path_talent_code.is_not(None))
        .order_by(Player.rating.desc(), UserCard.id).limit(30)
    )).scalars().all())


def _card_rating(card: UserCard, config) -> int:
    return _engine_card(card, config).player.rating


# --- squad -----------------------------------------------------------------------------

def _filler(club_name: str, slot, rating: int, n: int) -> dict:
    kid = pcc._academy(f"mgr:{club_name}", slot, rating, n)
    return {"slot": slot.code, "key": f"kid:{slot.code}", "kind": "kid", "ref": None, "name": kid["name"],
            "position": kid["position"], "rating": kid["rating"]}


async def build_pool(db: AsyncSession, club: ManagerClub, config) -> tuple[list[dict], dict]:
    """Everyone who may play: (entries, engine cards by entry key). Entries
    carry what the pitch draws: `appearance` / `number` of a «Мой игрок»,
    `photo` (static path) of a card."""
    entries: list[dict] = []
    cards: dict[str, SimpleNamespace] = {}
    contracts = await _contracts(db, club.id)
    mps = await _my_players(db, {club.owner_id, *(c.user_id for c in contracts)})

    def looks(uid: int) -> dict:
        mp = mps.get(uid)
        return {"appearance": dict(mp.appearance or {}), "number": mp.number} if mp else {}

    owner_contract = await _active_contract(db, club.owner_id)
    if owner_contract is None or owner_contract.club_id == club.id:
        card = await my_player_service.engine_card(db, club.owner_id, config)
        if card is not None:
            entries.append({"key": f"own:{club.owner_id}", "kind": "own", "ref": club.owner_id, "user_id": club.owner_id,
                            "name": card.player.display_name, "position": card.player.position.value, "rating": card.player.rating,
                            **looks(club.owner_id)})
            cards[f"own:{club.owner_id}"] = card
    academy = await _academy_card(db, club)
    if academy is not None:
        engine = _engine_card(academy, config)
        entries.append({"key": f"academy:{academy.id}", "kind": "academy", "ref": academy.id, "name": engine.player.display_name,
                        "position": engine.player.position.value, "rating": engine.player.rating,
                        "photo": academy.player.image_path})
        cards[f"academy:{academy.id}"] = engine
    users = await _users(db, [c.user_id for c in contracts])
    for c in contracts:
        if c.user_id == club.owner_id:
            continue
        card = await my_player_service.engine_card(db, c.user_id, config)
        if card is None:
            continue
        key = f"live:{c.id}"
        entries.append({"key": key, "kind": "live", "ref": c.id, "user_id": c.user_id, "owner_name": _name(users.get(c.user_id)),
                        "name": card.player.display_name, "position": card.player.position.value, "rating": card.player.rating,
                        "loan": c.kind == "loan", **looks(c.user_id)})
        cards[key] = card
    npcs = await _npcs(db, club.id)
    players = {p.id: p for p in (await db.execute(select(Player).where(Player.id.in_({n.player_id for n in npcs} or {0})))).scalars().all()}
    for n in npcs:
        p = players.get(n.player_id)
        if p is None:
            continue
        entries.append({"key": f"npc:{n.id}", "kind": "npc", "ref": n.id, "player_id": p.id, "name": p.display_name,
                        "position": p.position.value, "rating": p.rating, "loan": n.kind == "loan", "auto": n.auto,
                        "photo": p.image_path})
    return entries, cards


def pick_xi(entries: list[dict], club_name: str, filler_rating: int, formation: str = DEFAULT_FORMATION) -> tuple[list[dict], list[dict]]:
    """The formation's XI: the owner's own player and his academy card always
    start (at the best free slot of their line), then the strongest of the
    rest (ideal position first); the others sit on the bench; empty slots
    get academy kids."""
    slots = get_formation_slots(tactics.clean_formation(formation))
    taken: dict[str, dict] = {}
    bench = []
    priority = {"own": 0, "academy": 1}
    # .get: academy kids frozen into season state before they carried a key.
    for e in sorted(entries, key=lambda x: (priority.get(x["kind"], 2), -x["rating"], x.get("key", ""))):
        position = Position(e["position"])
        free = [s for s in slots if s.category == _category(position) and s.code not in taken]
        ideal = [s for s in free if on_ideal_position(position, s.ideal_position)]
        slot = (ideal or free or [None])[0]
        if slot is None:
            bench.append(e)
        else:
            taken[slot.code] = {**e, "slot": slot.code}
    for n, slot in enumerate(s for s in slots if s.code not in taken):
        taken[slot.code] = _filler(club_name, slot, filler_rating, n)
    return [taken[s.code] for s in slots], bench


def _avg(xi: list[dict]) -> int:
    return round(sum(p["rating"] for p in xi) / len(xi)) if xi else 50


def _division_rating(division: int, config) -> int:
    return _pick(config.manager_division_rating, division - 1, 62)


async def squad_view(db: AsyncSession, club: ManagerClub, config) -> dict:
    entries, _ = await build_pool(db, club, config)
    xi, bench = pick_xi(entries, club.name, _division_rating(club.division, config) - FILLER_GAP, club.formation)
    contracts = {c.id: c for c in await _contracts(db, club.id)}
    for p in (*xi, *bench):
        if p["kind"] == "live":
            p["value"] = live_value(p["rating"], contracts.get(p["ref"]), config)  # form at the club counts
        elif p["kind"] != "kid":
            p["value"] = value_of(p["rating"], config)
    return {"xi": xi, "bench": bench, "rating": _avg(xi), "kids": sum(1 for p in xi if p["kind"] == "kid"),
            "formation": tactics.clean_formation(club.formation)}


# What a frozen season roster keeps of an entry (no pictures, no engine cards).
ROSTER_KEYS = ("key", "kind", "ref", "user_id", "player_id", "name", "position", "rating", "loan", "auto")


def _engine_for(entry: dict, cards: dict, index: int, i: int, club_name: str, line: str, mods: dict, config):
    mine = cards.get(entry.get("key")) if entry["kind"] in ("own", "live") else None
    if mine is not None:
        card = _engine_card(mine, config)
        card.boosts = getattr(mine, "boosts", None)
        card.player.rating = tactics.apply(card.player.rating, line, mods)
        return card
    player = SimpleNamespace(
        display_name=entry["name"], position=Position(entry["position"]), rating=tactics.apply(entry["rating"], line, mods),
        rarity=Rarity.common, club=club_name, country="", attack_rating=None, defense_rating=None,
    )
    return _EngineCard(id=-(500_000 + index * 100 + i + 1), player_id=entry.get("player_id") or 0, player=player)


def _side_from(xi: list[dict], cards: dict, index: int, club_name: str, formation: str, mods: dict, config):
    """Engine side with the neutral engine tactics; the club's own tactics
    are already in the ratings (`mods`, manager_tactics.modifiers)."""
    slots = {s.code: s for s in get_formation_slots(tactics.clean_formation(formation))}
    with_slots = [
        (_engine_for(p, cards, index, i, club_name, slots[p["slot"]].category, mods, config), slots[p["slot"]])
        for i, p in enumerate(xi)
    ]
    side = build_side(with_slots, tactics.ENGINE_MENTALITY, tactics.ENGINE_PLAYSTYLE)
    lineup = [
        {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category, **({"skill": c.skill} if c.skill else {}),
         **({"boosts": c.boosts} if getattr(c, "boosts", None) else {})}
        for c, slot in with_slots
    ]
    return side, lineup


# --- club ------------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    name = " ".join((name or "").split())
    if not NAME_MIN <= len(name) <= NAME_MAX:
        raise ConflictError(f"Название клуба — от {NAME_MIN} до {NAME_MAX} символов")
    return name


async def found_club(db: AsyncSession, user: User, name: str, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    _enabled(config)
    now = now or datetime.now(timezone.utc)
    name = _clean_name(name)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    if await _owned_club(db, user.id):
        raise ConflictError("У тебя уже есть клуб")
    if await my_player_service.get_my_player(db, user.id) is None:
        raise ConflictError("Сначала создай «Моего игрока»")
    if _level(locked, config) < config.manager_min_level:
        raise ConflictError(f"Клуб можно основать с {config.manager_min_level} уровня «Моего игрока»")
    if locked.is_trade_banned:
        raise ForbiddenError("Тебе закрыты выплаты другим игрокам — клуб основать нельзя")
    if reason := await trade_guard_service.give_block_reason(db, locked, config):
        raise ConflictError(f"Клуб платит зарплаты другим игрокам, поэтому для него действуют правила обменов. {reason}")
    division = entry_division(config)
    club = ManagerClub(owner_id=user.id, name=name, division=division, best_division=division, budget=0, look={})
    db.add(club)
    await db.flush()
    await _grant_budget(db, club, season_key(now), config)
    if config.manager_found_cost > 0:
        await wallet_service.debit_coins(
            db, locked, config.manager_found_cost, TransactionType.manager_club_found, f"Основание клуба «{name}»",
            related_object_type=RELATED, related_object_id=club.id,
        )
    await db.commit()
    return await get_view(db, user, now)


async def update_club(
    db: AsyncSession, user: User, name: Optional[str], formation: Optional[str], style: Optional[str],
    academy_card_id: Optional[int] = None, clear_academy: bool = False,
) -> dict:
    """Name, tactics (any time — also during a season) and the academy card
    (only between seasons)."""
    club = await _owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("У тебя нет клуба")
    if name is not None:
        club.name = _clean_name(name)
    if formation is not None:
        if formation not in tactics.FORMATIONS:
            raise ConflictError("Неизвестная схема")
        club.formation = formation
    if style is not None:
        if style not in tactics.STYLES:
            raise ConflictError("Неизвестный стиль")
        club.style = style
    if academy_card_id is not None or clear_academy:
        await _ensure_window(db, club)
        if clear_academy:
            club.academy_card_id = None
        else:
            card = (await db.execute(
                select(UserCard).options(selectinload(UserCard.player)).where(UserCard.id == academy_card_id)
            )).scalar_one_or_none()
            if card is None or card.owner_id != user.id or card.player is None or card.player.path_talent_code is None:
                raise ConflictError("Это не карточка твоей «Академии»")
            club.academy_card_id = card.id
    await db.commit()
    return await get_view(db, user)


# --- users' players: offers & transfers ------------------------------------------------------

async def _live_count(db: AsyncSession, club_id: int, owner_id: int) -> int:
    rows = await _contracts(db, club_id, ("active", "offered"))
    return sum(1 for c in rows if c.user_id != owner_id)


async def _squad_size(db: AsyncSession, club: ManagerClub) -> int:
    return await _live_count(db, club.id, club.owner_id) + len(await _npcs(db, club.id))


async def make_offer(
    db: AsyncSession, user: User, target_id: int, wage: int, seasons: int, fee: int = 0, kind: Optional[str] = None,
) -> dict:
    """Sign a free agent, or offer another club a transfer / a season loan
    for its player (fee in euros to its budget) — with the player's terms
    (coins per season)."""
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    _enabled(config)
    if target_id == user.id:
        raise ConflictError("Твой «Мой игрок» и так играет за твой клуб")
    club = await _owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    await _ensure_window(db, club)
    target = await wallet_service.lock_user_for_update(db, target_id)
    mp = await my_player_service.get_my_player(db, target_id)
    if mp is None or target.is_banned:
        raise NotFoundError("Игрок не найден")
    if _level(target, config) < config.manager_min_level:
        raise ConflictError(f"Подписывать можно игроков с {config.manager_min_level} уровня")
    current = await _active_contract(db, target_id)
    if current is not None and current.club_id == club.id:
        raise ConflictError("Он уже играет за тебя")
    # An owner's own «Мой игрок» without a contract is a free agent for everyone else.
    seller = await db.get(ManagerClub, current.club_id) if current else None
    kind = kind or ("sign" if current is None else "transfer")
    if current is None:
        if kind != "sign":
            raise ConflictError("Игрок свободен — ему можно просто предложить контракт")
        fee = 0
        if not mp.market_open and target_id not in set(await friend_ids(db, user.id)):
            raise ConflictError("Игрок не ищет клуб — предложить контракт можно только другу")
    else:
        if kind not in ("transfer", "loan"):
            raise ConflictError("Игрок в клубе — его можно купить или взять в аренду")
        if current.kind == "loan":
            raise ConflictError("Игрок в аренде — подожди, пока он вернётся в свой клуб")
        await _ensure_window(db, seller, f"Клуб «{seller.name}»")
        value = live_value(my_player_service.rating_of(mp, config), current, config)
        low, high = (value // 2, value * 3) if kind == "transfer" else (0, value)
        if not low <= fee <= high:
            raise ConflictError(f"Сумма {'трансфера' if kind == 'transfer' else 'аренды'} — от {money(low)} до {money(high)}")
        if kind == "loan":
            seasons = 1
    if seasons not in CONTRACT_SEASONS:
        raise ConflictError("Контракт — на 1, 2 или 3 сезона")
    wage = int(wage)
    if not 0 <= wage <= config.manager_live_wage_max:
        raise ConflictError(f"Зарплата — от 0 до {config.manager_live_wage_max} монет за сезон")
    if target.is_trade_banned and wage > 0:
        raise ConflictError("Этому игроку нельзя платить зарплату — только контракт за 0")
    pending = await _contracts(db, club.id, ("offered",))
    if any(c.user_id == target_id for c in pending):
        raise ConflictError("Этому игроку уже отправлено предложение")
    if await _live_count(db, club.id, club.owner_id) >= config.manager_max_live:
        raise ConflictError(f"В клубе не больше {config.manager_max_live} игроков других пользователей вместе с предложениями")
    if await _squad_size(db, club) >= config.manager_squad_max:
        raise ConflictError(f"В заявке не больше {config.manager_squad_max} игроков")
    need = fee + wage_eur(wage, config)
    if need > club.budget:
        raise ConflictError(f"Не хватает бюджета: нужно {money(need)} (сумма + зарплата за сезон), есть {money(club.budget)}")
    contract = ManagerContract(
        club_id=club.id, user_id=target_id, kind=kind, status="offered", fee=fee, wage=wage,
        seasons_total=seasons, seasons_left=seasons, club_agreed=current is None,
        from_contract_id=current.id if current else None,
    )
    db.add(contract)
    await db.flush()
    terms = f"{wage} монет за сезон, {seasons} сез."
    await notify(
        db, target_id, NotificationType.manager_event, f"«{club.name}» хочет тебя ✍️",
        f"{_name(user)} предлагает {mp.name} " + ({"sign": "контракт", "transfer": "переход", "loan": "аренду"}[kind]) + f": {terms}",
        related_object_type=RELATED, related_object_id=club.id,
    )
    if seller is not None:
        await notify(
            db, seller.owner_id, NotificationType.manager_event, f"Запрос на {mp.name} 💰",
            f"«{club.name}» предлагает {money(fee)} за {'переход' if kind == 'transfer' else 'аренду на сезон'}",
            related_object_type=RELATED, related_object_id=seller.id,
        )
    await db.commit()
    return await get_view(db, user)


def money(eur: int) -> str:
    """€4,5 млн / €800 тыс."""
    if abs(eur) >= 1_000_000:
        return f"€{eur / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + " млн"
    if abs(eur) >= 1_000:
        return f"€{round(eur / 1000)} тыс"
    return f"€{eur}"


async def cancel_offer(db: AsyncSession, user: User, contract_id: int) -> dict:
    club = await _owned_club(db, user.id, lock=True)
    contract = await db.get(ManagerContract, contract_id)
    if club is None or contract is None or contract.club_id != club.id:
        raise NotFoundError("Предложение не найдено")
    if contract.status != "offered":
        raise ConflictError("Предложение уже неактуально")
    contract.status = "cancelled"
    contract.decided_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_view(db, user)


async def respond_offer(db: AsyncSession, user: User, contract_id: int, accept: bool) -> dict:
    """The player answers, or — for a transfer/loan — the selling club's
    owner. Both yes → the deal is done."""
    config = await get_config(db)
    found = await db.get(ManagerContract, contract_id)
    if found is None:
        raise NotFoundError("Предложение не найдено")
    parent = await db.get(ManagerContract, found.from_contract_id) if found.from_contract_id else None
    clubs = await _lock_clubs(db, [found.club_id, parent.club_id if parent else None])
    buyer = clubs[found.club_id]
    seller = clubs.get(parent.club_id) if parent else None
    as_player = found.user_id == user.id
    as_seller = seller is not None and seller.owner_id == user.id
    if not as_player and not as_seller:
        raise NotFoundError("Предложение не найдено")
    player_user = await wallet_service.lock_user_for_update(db, found.user_id)
    contract = (await db.execute(
        select(ManagerContract).where(ManagerContract.id == contract_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if contract.status != "offered":
        raise ConflictError("Предложение уже неактуально")
    now = datetime.now(timezone.utc)
    mp = await my_player_service.get_my_player(db, contract.user_id)
    player_name = mp.name if mp else _name(player_user)
    if not accept:
        contract.status = "declined"
        contract.decided_at = now
        who = player_name if as_player else f"«{seller.name}»"
        await notify(
            db, buyer.owner_id, NotificationType.manager_event, f"{who}: отказ",
            f"Сделка по {player_name} с «{buyer.name}» не состоялась", related_object_type=RELATED, related_object_id=buyer.id,
        )
        await db.commit()
        return await get_view(db, user)
    if as_seller:
        contract.club_agreed = True
    if as_player:
        contract.player_agreed = True
    if not (contract.club_agreed and contract.player_agreed):
        if as_seller:
            await notify(
                db, buyer.owner_id, NotificationType.manager_event, f"«{seller.name}» согласен ✅",
                f"Клуб отпускает {player_name}. Осталось согласие игрока", related_object_type=RELATED, related_object_id=buyer.id,
            )
            await notify(
                db, contract.user_id, NotificationType.manager_event, f"Твой клуб согласен на переход в «{buyer.name}»",
                "Решение за тобой", related_object_type=RELATED, related_object_id=buyer.id,
            )
        await db.commit()
        return await get_view(db, user)
    await _execute(db, contract, buyer, seller, parent, player_user, player_name, config, now)
    await db.commit()
    return await get_view(db, user)


async def _execute(db, contract, buyer, seller, parent, player_user, player_name, config, now) -> None:
    _enabled(config)
    await _ensure_window(db, buyer, f"Клуб «{buyer.name}»")
    if seller is not None:
        await _ensure_window(db, seller, f"Клуб «{seller.name}»")
        if parent is None or parent.status != "active" or parent.club_id != seller.id:
            raise ConflictError("Игрок уже не в том клубе — сделка неактуальна")
    elif await _active_contract(db, contract.user_id):
        raise ConflictError("У игрока уже есть клуб")
    if player_user.is_trade_banned and contract.wage > 0:
        raise ConflictError("Этому игроку нельзя получать зарплату от других игроков")
    if contract.fee > buyer.budget:
        raise ConflictError(f"У «{buyer.name}» не хватает бюджета на сделку")
    if contract.fee:
        buyer.budget -= contract.fee
        seller.budget += contract.fee
    if parent is not None:
        parent.status = "on_loan" if contract.kind == "loan" else "ended"
        parent.decided_at = now
    contract.status = "active"
    contract.decided_at = now
    contract.club_agreed = True
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == contract.user_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is not None:
        mp.market_open = False
    for other in (await db.execute(
        select(ManagerContract).where(ManagerContract.user_id == contract.user_id, ManagerContract.status == "offered",
                                      ManagerContract.id != contract.id)
    )).scalars().all():
        other.status = "declined"
        other.decided_at = now
    what = {"sign": "подписал контракт с", "transfer": "перешёл в", "loan": "ушёл в аренду в"}[contract.kind]
    text = f"{player_name} {what} «{buyer.name}»" + (f" за {money(contract.fee)}" if contract.fee else "")
    for target in {buyer.owner_id, contract.user_id, *([seller.owner_id] if seller else [])}:
        await notify(db, target, NotificationType.manager_event, "Here we go! ✍️", text,
                     related_object_type="manager_contract", related_object_id=contract.id)


async def end_contract(db: AsyncSession, user: User, contract_id: int) -> dict:
    """The player leaves or the club releases him — not during a season.
    Ending a loan sends him back to his club."""
    found = await db.get(ManagerContract, contract_id)
    if found is None:
        raise NotFoundError("Контракт не найден")
    clubs = await _lock_clubs(db, [found.club_id])
    club = clubs[found.club_id]
    contract = (await db.execute(
        select(ManagerContract).where(ManagerContract.id == contract_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    is_owner = club.owner_id == user.id
    if not is_owner and contract.user_id != user.id:
        raise ForbiddenError("Это не твой контракт")
    if contract.status != "active":
        raise ConflictError("Контракт уже закончился")
    await _ensure_window(db, club, f"Клуб «{club.name}»")
    now = datetime.now(timezone.utc)
    await _close_contract(db, contract, now)
    other = contract.user_id if is_owner else club.owner_id
    mp = await my_player_service.get_my_player(db, contract.user_id)
    name = mp.name if mp else "Игрок"
    await notify(
        db, other, NotificationType.manager_event,
        f"«{club.name}» отпустил {name}" if is_owner else f"{name} ушёл из «{club.name}»",
        "Контракт расторгнут", related_object_type=RELATED, related_object_id=club.id,
    )
    await db.commit()
    return await get_view(db, user)


async def _close_contract(db: AsyncSession, contract: ManagerContract, now: datetime) -> None:
    contract.status = "ended"
    contract.decided_at = now
    if contract.kind == "loan" and contract.from_contract_id:
        parent = (await db.execute(
            select(ManagerContract).where(ManagerContract.id == contract.from_contract_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if parent is not None and parent.status == "on_loan":
            parent.status = "active" if parent.seasons_left > 0 else "ended"
            parent.decided_at = now


async def set_market(db: AsyncSession, user: User, open_: bool) -> dict:
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is None:
        raise ConflictError("Сначала создай «Моего игрока»")
    if open_ and await _active_contract(db, user.id):
        raise ConflictError("Ты уже в клубе — уйти можно в предсезонку")
    mp.market_open = open_
    await db.commit()
    return await get_view(db, user)


# --- catalog footballers ----------------------------------------------------------------------

async def _taken_players(db: AsyncSession) -> dict[int, int]:
    return {pid: cid for pid, cid in (await db.execute(
        select(ManagerNpc.player_id, ManagerNpc.club_id).where(ManagerNpc.status == "active")
    )).all()}


CATALOG_PAGE = 40


def affordable_rating(budget: int, deal: str, config, division: Optional[int], discount_pct: int) -> int:
    """The highest rating whose price (the fee + a season's wage) fits the
    budget; 0 when nobody does. Prices only grow with the rating."""
    best = 0
    for rating in range(1, 100):
        terms = npc_terms(rating, config, division, discount_pct)
        if (terms["value"] if deal == "buy" else terms["loan_fee"]) + terms["wage_now"] > budget:
            break
        best = rating
    return best


async def npc_catalog(
    db: AsyncSession, user: User, line: Optional[str], query: Optional[str], offset: int = 0,
    afford: Optional[str] = None, sort: str = "rating", free_only: bool = False,
) -> dict:
    """The game's footballers with their prices for this club. `afford`
    ("loan" / "buy") keeps only those the club's budget pays for, `sort`
    "cheap" starts from the weakest, `free_only` hides those other clubs hold."""
    config = await get_config(db)
    mine = await _owned_club(db, user.id)
    discount = (await base_snapshot(db, mine.owner_id, config))["discount_pct"] if mine else 0
    taken = await _taken_players(db)
    stmt = select(Player).where(Player.is_active.is_(True), Player.path_talent_code.is_(None))
    if line in LINES:
        stmt = stmt.where(Player.position.in_(CATEGORY_POSITIONS[line]))
    if query:
        stmt = stmt.where(Player.display_name.ilike(f"%{query.strip()[:40]}%"))
    max_rating = None
    if afford in ("loan", "buy") and mine:
        max_rating = affordable_rating(mine.budget, afford, config, mine.division, discount)
        stmt = stmt.where(Player.rating <= max_rating)
    if free_only and taken:
        stmt = stmt.where(Player.id.notin_(list(taken)))
    order = (Player.rating.asc(), Player.id) if sort == "cheap" else (Player.rating.desc(), Player.id)
    rows = (await db.execute(stmt.order_by(*order).offset(max(0, offset)).limit(CATALOG_PAGE + 1))).scalars().all()
    more = len(rows) > CATALOG_PAGE
    rows = rows[:CATALOG_PAGE]
    club_names = {c.id: c.name for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_(set(taken.values()) or {0}))
    )).scalars().all()}
    return {"max_rating": max_rating, "more": more, "players": [
        {"player_id": p.id, "name": p.display_name, "position": p.position.value, "rating": p.rating, "club": p.club,
         "country": p.country, **npc_terms(p.rating, config, mine.division if mine else None, discount),
         "taken_by": club_names.get(taken[p.id]) if p.id in taken else None,
         "mine": bool(mine and taken.get(p.id) == mine.id)}
        for p in rows
    ]}


async def sign_npc(db: AsyncSession, user: User, player_id: int, kind: str, seasons: int = 1) -> dict:
    config = await get_config(db)
    _enabled(config)
    if kind not in ("buy", "loan"):
        raise ConflictError("Купить или взять в аренду")
    seasons = 1 if kind == "loan" else seasons
    if seasons not in CONTRACT_SEASONS:
        raise ConflictError("Контракт — на 1, 2 или 3 сезона")
    club = await _owned_club(db, user.id, lock=True)
    if club is None:
        raise NotFoundError("Сначала основай клуб")
    await _ensure_window(db, club)
    player = await db.get(Player, player_id)
    if player is None or not player.is_active or player.path_talent_code is not None:
        raise NotFoundError("Футболист не найден")
    if player_id in await _taken_players(db):
        raise ConflictError("Он уже играет за другой клуб")
    if await _squad_size(db, club) >= config.manager_squad_max:
        raise ConflictError(f"В заявке не больше {config.manager_squad_max} игроков")
    snap = await base_snapshot(db, club.owner_id, config)
    terms = npc_terms(player.rating, config, club.division, snap["discount_pct"])
    fee = terms["value"] if kind == "buy" else terms["loan_fee"]
    if fee + terms["wage_now"] > club.budget:
        raise ConflictError(f"Не хватает бюджета: нужно {money(fee + terms['wage_now'])} (сумма + зарплата за сезон), есть {money(club.budget)}")
    club.budget -= fee
    try:
        async with db.begin_nested():
            db.add(ManagerNpc(club_id=club.id, player_id=player.id, kind=kind, fee=fee, wage=terms["wage"], seasons_left=seasons))
    except IntegrityError:
        raise ConflictError("Его только что забрал другой клуб")
    await db.commit()
    return await get_view(db, user)


async def release_npc(db: AsyncSession, user: User, npc_id: int) -> dict:
    """Sell a bought footballer back (config.manager_sell_back_pct of his
    value) or end a loan early (no refund)."""
    config = await get_config(db)
    club = await _owned_club(db, user.id, lock=True)
    npc = await db.get(ManagerNpc, npc_id)
    if club is None or npc is None or npc.club_id != club.id or npc.status != "active":
        raise NotFoundError("Футболист не найден")
    await _ensure_window(db, club)
    player = await db.get(Player, npc.player_id)
    refund = npc_terms(player.rating, config)["sell_back"] if npc.kind == "buy" and player else 0
    club.budget += refund
    npc.status = "ended"
    npc.ended_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_view(db, user)


async def value_trends(db: AsyncSession, user_ids, current: dict[int, int]) -> dict[int, Optional[int]]:
    """% change of each value against the last recorded season start."""
    if not user_ids:
        return {}
    last: dict[int, int] = {}
    rows = (await db.execute(
        select(ManagerValueHistory).where(ManagerValueHistory.user_id.in_(set(user_ids)))
        .order_by(ManagerValueHistory.user_id, ManagerValueHistory.season_key.desc())
    )).scalars().all()
    for r in rows:
        last.setdefault(r.user_id, r.value)
    return {uid: (round((current[uid] - last[uid]) * 100 / last[uid]) if last.get(uid) else None) for uid in current}


async def market(db: AsyncSession, user: User) -> dict:
    """Users' players: free agents («Ищу клуб»), friends without a club and
    players of other clubs (transfer or loan)."""
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    friends = set(await friend_ids(db, user.id))
    contracts = {c.user_id: c for c in (await db.execute(
        select(ManagerContract).where(ManagerContract.status == "active")
    )).scalars().all()}
    clubs = {c.id: c for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_({c.club_id for c in contracts.values()} or {0}))
    )).scalars().all()}
    rows = (await db.execute(
        select(MyPlayer, User).join(User, User.id == MyPlayer.user_id)
        .where((MyPlayer.market_open.is_(True)) | (MyPlayer.user_id.in_((friends | set(contracts)) or {0})),
               MyPlayer.user_id != user.id, User.is_banned.is_(False))
    )).all()
    mine = await _owned_club(db, user.id)
    offered = {c.user_id for c in await _contracts(db, mine.id, ("offered",))} if mine else set()
    out = []
    for mp, u in rows:
        level = _level(u, config)
        if level < config.manager_min_level:
            continue
        c = contracts.get(mp.user_id)
        club = clubs.get(c.club_id) if c else None
        if club is not None and mine is not None and club.id == mine.id:
            continue
        rating = my_player_service.rating_of(mp, config)
        out.append({
            "user_id": mp.user_id, "player_name": mp.name, "owner_name": _name(u), "position": mp.position.value,
            "rating": rating, "level": level, "value": live_value(rating, c, config), "is_friend": mp.user_id in friends,
            "looking": bool(mp.market_open), "offered": mp.user_id in offered,
            "club": {"name": club.name, "seasons_left": c.seasons_left, "on_loan": c.kind == "loan", "division": club.division}
            if club else None,
        })
    trends = await value_trends(db, [p["user_id"] for p in out], {p["user_id"]: p["value"] for p in out})
    for p in out:
        p["trend_pct"] = trends.get(p["user_id"])
    out.sort(key=lambda p: (p["club"] is not None, not p["is_friend"], -p["rating"], p["user_id"]))
    return {"players": out[:80]}


# --- season start ------------------------------------------------------------------------

async def _expire(db: AsyncSession, club: ManagerClub, now: datetime) -> None:
    """Contracts and footballers whose seasons ran out leave (loans go back)."""
    for c in await _contracts(db, club.id):
        if c.seasons_left <= 0:
            await _close_contract(db, c, now)
            await notify(
                db, c.user_id, NotificationType.manager_event, f"Контракт с «{club.name}» закончился",
                f"{c.matches_played} матчей, ⚽ {c.goals}, заработано {c.earned} монет. Ты снова свободен",
                related_object_type=RELATED, related_object_id=club.id,
            )
    for c in await _contracts(db, club.id, ("on_loan",)):
        if c.seasons_left <= 0:
            c.status = "ended"
            c.decided_at = now
    for n in await _npcs(db, club.id):
        if n.seasons_left <= 0:
            n.status = "ended"
            n.ended_at = now


async def _prepare_club(db: AsyncSession, club: ManagerClub, key: str, now: datetime, taken: set[int], pool_by_line, config) -> dict:
    """Season start for one (locked) club: expiries, grant, wages,
    automatic signings, the frozen XI. Returns the team entry."""
    await _expire(db, club, now)
    await _grant_budget(db, club, key, config)
    snap = await base_snapshot(db, club.owner_id, config)
    notes = []
    for c in await _contracts(db, club.id):
        wage = min(c.wage, config.manager_live_wage_max)
        cost = wage_eur(wage, config)
        if cost > club.budget:
            await _close_contract(db, c, now)
            notes.append("не хватило бюджета на зарплату — контракт с игроком расторгнут")
            await notify(db, c.user_id, NotificationType.manager_event, f"«{club.name}» не смог платить",
                         "Клуб не выплатил зарплату — контракт расторгнут, ты свободен",
                         related_object_type=RELATED, related_object_id=club.id)
            continue
        if wage > 0:
            club.budget -= cost
            c.earned += wage
            locked = await wallet_service.lock_user_for_update(db, c.user_id)
            await wallet_service.credit_coins(
                db, locked, wage, TransactionType.manager_salary, f"Зарплата в «{club.name}» за сезон",
                related_object_type=RELATED, related_object_id=club.id,
            )
        c.seasons_left -= 1
    for c in await _contracts(db, club.id, ("on_loan",)):
        c.seasons_left -= 1
    wage_pct = _pct(config.manager_division_wage_pct, club.division)
    for n in await _npcs(db, club.id):
        pay = n.wage * wage_pct // 100 * (100 - snap["discount_pct"]) // 100
        if pay > club.budget:
            n.status = "ended"
            n.ended_at = now
            notes.append("одному футболисту не хватило на зарплату — он ушёл")
            continue
        club.budget -= pay
        n.seasons_left -= 1
    target = _division_rating(club.division, config)
    entries, _ = await build_pool(db, club, config)
    xi, _bench = pick_xi(entries, club.name, target - FILLER_GAP, club.formation)
    signed = 0
    slots = {s.code: s for s in get_formation_slots(tactics.clean_formation(club.formation))}
    for i, p in enumerate(xi):
        if p["kind"] != "kid":
            continue
        slot = slots[p["slot"]]
        options = [pl for pl in pool_by_line.get(slot.category, []) if pl.id not in taken and abs(pl.rating - target) <= AUTO_RANGE]
        options.sort(key=lambda pl: (not on_ideal_position(pl.position, slot.ideal_position), abs(pl.rating - target), pl.id))
        for pl in options[:6]:
            terms = npc_terms(pl.rating, config, club.division, snap["discount_pct"])
            cost = terms["loan_fee"] + terms["wage_now"]
            if cost > club.budget:
                continue
            club.budget -= cost
            taken.add(pl.id)
            npc = ManagerNpc(club_id=club.id, player_id=pl.id, kind="loan", fee=terms["loan_fee"], wage=terms["wage"],
                             seasons_left=0, auto=True)
            db.add(npc)
            await db.flush()
            xi[i] = {"slot": slot.code, "key": f"npc:{npc.id}", "kind": "npc", "ref": npc.id, "player_id": pl.id,
                     "name": pl.display_name, "position": pl.position.value, "rating": pl.rating, "loan": True, "auto": True}
            entries.append(xi[i])
            signed += 1
            break
    if signed:
        notes.append(f"система взяла в аренду {signed} футбол.")
    kids = sum(1 for p in xi if p["kind"] == "kid")
    if kids:
        notes.append(f"{kids} мест заняли воспитанники")
    # The season roster is frozen (no trading during a season); the XI is
    # picked from it every round with the club's formation of that moment.
    roster = [{k: e[k] for k in ROSTER_KEYS if k in e} for e in entries]
    return {"club": club, "xi": [{k: p[k] for k in (*ROSTER_KEYS, "slot") if k in p} for p in xi], "roster": roster,
            "filler": target - FILLER_GAP, "rating": _avg(xi), "notes": notes, "base": snap}


def _bot_team(index: int, club: dict) -> dict:
    rng = random.Random(pcc._seed(f"manager-bot:{club['key']}"))
    return {
        "index": index, "club_id": None, "owner_id": None, "owner_name": None, "key": club["key"], "name": club["name"],
        "rating": club["rating"], "players": club["squad"], "formation": "4-3-3", "style": rng.choice(tactics.STYLES),
    }


async def _record_values(db: AsyncSession, key: str, config) -> None:
    """Every «Мой игрок»'s value at the season start (the ▲/▼ trend)."""
    done = set((await db.execute(select(ManagerValueHistory.user_id).where(ManagerValueHistory.season_key == key))).scalars().all())
    contracts = {c.user_id: c for c in (await db.execute(
        select(ManagerContract).where(ManagerContract.status == "active")
    )).scalars().all()}
    for mp in (await db.execute(select(MyPlayer))).scalars().all():
        if mp.user_id in done:
            continue
        rating = my_player_service.rating_of(mp, config)
        db.add(ManagerValueHistory(user_id=mp.user_id, season_key=key, value=live_value(rating, contracts.get(mp.user_id), config),
                                   rating=rating))


async def ensure_season(db: AsyncSession, now: Optional[datetime] = None) -> bool:
    """Starts this week's season once its preseason is over. True if it
    started now."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    if not config.manager_enabled or now < preseason_end(now, config):
        return False
    key = season_key(now)
    if await db.get(ManagerSeason, key) is not None:
        return False
    await pcc.prepare(db, config)  # commits — before any lock
    # In UTC: SQLite compares timestamps as text, so a local-offset bound
    # would let clubs founded after the preseason into this season.
    starts = preseason_end(now, config).astimezone(timezone.utc)
    club_ids = (await db.execute(
        select(ManagerClub.id).where(ManagerClub.created_at < starts).order_by(ManagerClub.id)
    )).scalars().all()
    try:
        async with db.begin_nested():
            db.add(ManagerSeason(key=key, started_at=now, depth=depth_of(config)))
    except IntegrityError:
        return False
    size = league_size(config)
    schedule = season_schedule(max(now, starts), config)
    clubs = await _lock_clubs(db, club_ids)
    taken = set(await _taken_players(db))
    pool_by_line: dict[str, list[Player]] = {}
    for p in (await db.execute(
        select(Player).where(Player.is_active.is_(True), Player.path_talent_code.is_(None)).order_by(Player.rating.desc(), Player.id)
    )).scalars().all():
        pool_by_line.setdefault(_category(p.position), []).append(p)
    prepared = [await _prepare_club(db, club, key, now, taken, pool_by_line, config) for club in clubs.values()]
    catalog = await pcc.club_catalog(db, config)
    owners = await _users(db, [p["club"].owner_id for p in prepared])
    for division in sorted({p["club"].division for p in prepared}):
        group_all = sorted((p for p in prepared if p["club"].division == division), key=lambda p: (-p["rating"], p["club"].id))
        for start in range(0, len(group_all), size):
            group = group_all[start:start + size]
            teams = []
            for p in group:
                club = p["club"]
                teams.append({
                    "index": len(teams), "club_id": club.id, "owner_id": club.owner_id,
                    "owner_name": _name(owners.get(club.owner_id)), "key": f"mc:{club.id}", "name": club.name,
                    "rating": p["rating"], "players": None, "xi": p["xi"], "roster": p["roster"], "filler": p["filler"],
                    "base": p["base"],
                })
            names = {t["name"] for t in teams}
            # Bots as strong as the league's own clubs — not the division's «ideal».
            target = round(sum(t["rating"] for t in teams) / len(teams))
            bots = sorted((c for c in catalog if c["name"] not in names), key=lambda c: (abs(c["rating"] - target), c["key"]))
            for bot in bots[: size - len(teams)]:
                teams.append(_bot_team(len(teams), bot))
            while len(teams) < size:
                filler = pcc.academy_fillers({"key": f"mgr:{key}:{division}:{start}:{len(teams)}", "rating": target,
                                              "league": None, "level": None},
                                             1, {t["name"] for t in teams}, config)[0]
                teams.append(_bot_team(len(teams), filler))
            league = ManagerLeague(season_key=key, division=division, status="active", started_at=now, state={
                "teams": teams, "fixtures": circle_round_robin(size), "schedule": schedule,
                "results": [], "players": {},
            })
            db.add(league)
            await db.flush()
            first = ensure_aware(datetime.fromisoformat(schedule[0])).astimezone(app_timezone())
            for p in group:
                club = p["club"]
                club.league_id = league.id
                await notify(
                    db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: сезон начался ⚽",
                    f"{division_name(division)}, {rounds_of(config)} туров, первый — {first.strftime('%d.%m %H:%M')}"
                    + (f". {'; '.join(p['notes'])}" if p["notes"] else ""),
                    related_object_type=RELATED, related_object_id=club.id,
                )
    await _record_values(db, key, config)
    await db.commit()
    return True


# --- rounds ------------------------------------------------------------------------------

async def _lock_league(db: AsyncSession, league_id: int) -> ManagerLeague:
    league = (await db.execute(
        select(ManagerLeague).where(ManagerLeague.id == league_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if league is None:
        raise NotFoundError("Лига не найдена")
    return league


def _goal_events(match, lineups: dict[str, list[dict]]) -> list[dict]:
    names = {side: {p["club_card_id"]: p["name"] for p in lineup} for side, lineup in lineups.items()}
    out = []
    for e in match.event_log:
        if e.get("event_type") != "goal":
            continue
        side = e.get("team")
        shooter = (e.get("payload") or {}).get("shooter_id")
        out.append({"team": side, "minute": e.get("minute"), "name": names.get(side, {}).get(shooter, "")})
    return out


async def _live_cards(db: AsyncSession, xi: list[dict], config) -> dict:
    cards = {}
    for p in xi:
        if p["kind"] in ("own", "live") and p.get("user_id"):
            card = await my_player_service.engine_card(db, p["user_id"], config)
            if card is not None:
                cards[p["key"]] = card
    return cards


async def _play_round(db: AsyncSession, league: ManagerLeague, round_index: int, config) -> None:
    from app.services import player_career_cups as cups
    from app.services.player_career_service import _match_rating

    state = copy.deepcopy(league.state)
    teams = state["teams"]
    schedule = state.get("schedule") or []
    at = ensure_aware(datetime.fromisoformat(schedule[round_index])) if round_index < len(schedule) else datetime.now(timezone.utc)
    clubs = await _lock_clubs(db, [t["club_id"] for t in teams if t["club_id"]])
    plan: dict[int, dict] = {}
    for t in teams:
        if t["club_id"]:
            # The frozen roster, today's form of the «Мои игроки», the club's
            # formation and style of this moment (tactics may change mid-season).
            club = clubs[t["club_id"]]
            # An empty roster is a real «nobody but academy kids» squad — only
            # states frozen before rosters existed fall back to the XI.
            roster = [dict(e) for e in (t["roster"] if "roster" in t else t["xi"])]
            live = await _live_cards(db, roster, config)
            for e in roster:
                if e.get("key") in live:
                    e["rating"] = live[e["key"]].player.rating
            xi, _bench = pick_xi(roster, club.name, t.get("filler", 50), club.formation)
            t["xi"] = xi
            plan[t["index"]] = {"xi": xi, "cards": live, "formation": tactics.clean_formation(club.formation),
                                "style": tactics.clean_style(club.style), "name": club.name}
        else:
            plan[t["index"]] = {"xi": [{**p, "kind": "bot"} for p in t["players"]], "cards": {},
                                "formation": t.get("formation") or DEFAULT_FORMATION,
                                "style": tactics.clean_style(t.get("style")), "name": t["name"]}
    rng = random.Random(league.id * 7919 + round_index)
    results = []
    for home, away in state["fixtures"][round_index]:
        sides = {}
        for idx, opp in ((home, away), (away, home)):
            p = plan[idx]
            mods = tactics.modifiers(p["style"], p["formation"], plan[opp]["style"], config)
            sides[idx] = _side_from(p["xi"], p["cards"], idx, p["name"], p["formation"], mods, config)
        match = tournament_match_engine.simulate_match(
            sides[home][0], sides[away][0], sides[home][1], sides[away][1], config, teams[home]["name"], teams[away]["name"],
        )
        results.append({
            "home": home, "away": away, "hs": match.score_a, "as": match.score_b,
            "goals": _goal_events(match, {"a": sides[home][1], "b": sides[away][1]}),
            "styles": [plan[home]["style"], plan[away]["style"]],
            "formations": [plan[home]["formation"], plan[away]["formation"]],
        })
        for idx, side in ((home, "a"), (away, "b")):
            t = teams[idx]
            if not t["club_id"]:
                continue
            await _settle_match(db, clubs[t["club_id"]], t, sides[idx][1], match, side, idx == home, league.division,
                                at, rng, config, state, _match_rating, cups)
    state["results"].append(results)
    league.state = state
    flag_modified(league, "state")
    league.rounds_played = round_index + 1
    if league.rounds_played >= len(state["fixtures"]):
        await _finish(db, league, config)
    elif _local_day(schedule, round_index) != _local_day(schedule, round_index + 1):
        # The day's last round: one digest (the season's last day ends with the final message).
        today = sum(1 for i in range(league.rounds_played) if _local_day(schedule, i) == _local_day(schedule, round_index))
        await _daily_digest(db, league, today)


async def _settle_match(db, club, team, lineup, match, side, home, division, at, rng, config, state, match_rating, cups) -> None:
    own, opp = (match.score_a, match.score_b) if side == "a" else (match.score_b, match.score_a)
    income = config.manager_income_win if own > opp else config.manager_income_draw if own == opp else config.manager_income_loss
    club.budget += income * _pct(config.manager_division_income_pct, division) // 100
    if home:
        club.budget += ticket_income(division, team.get("base") or {}, config)
    for p, line_card in zip(team["xi"], lineup):
        card_id = line_card["club_card_id"]
        goals = sum(1 for e in match.event_log if e.get("event_type") == "goal" and e.get("team") == side
                    and (e.get("payload") or {}).get("shooter_id") == card_id)
        assists = sum(1 for e in match.event_log if e.get("event_type") == "goal" and e.get("team") == side
                      and (e.get("payload") or {}).get("assist_id") == card_id)
        if p["kind"] == "npc" and goals:
            npc = await db.get(ManagerNpc, p["ref"])
            if npc is not None:
                npc.goals += goals
        if p["kind"] not in ("own", "live"):
            continue
        uid = p["user_id"]
        line = line_card["category"]
        rating = match_rating(goals, assists, own, opp, rng, line)
        totals = state["players"].setdefault(str(uid), {
            "name": p["name"], "team_index": team["index"], "matches": 0, "goals": 0, "assists": 0, "rating_sum": 0.0,
        })
        totals["matches"] += 1
        totals["goals"] += goals
        totals["assists"] += assists
        totals["rating_sum"] = round(totals["rating_sum"] + rating, 2)
        if p["kind"] == "live":
            contract = await db.get(ManagerContract, p["ref"])
            if contract is not None:
                contract.matches_played += 1
                contract.goals += goals
                contract.assists += assists
        locked = await wallet_service.lock_user_for_update(db, uid)
        my_player_service.add_xp(locked, config.manager_match_xp, config, bonus_pct=await my_player_service.xp_bonus_pct(db, uid))
        if config.manager_freshness_cost > 0:
            mp = (await db.execute(
                select(MyPlayer).where(MyPlayer.user_id == uid).with_for_update().execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if mp is not None:
                fresh = my_player_service.freshness_now(mp, config, at, await my_player_service.regen_bonus(db, uid))
                my_player_service.set_freshness(mp, fresh - config.manager_freshness_cost, at)
        await cups.record_match(db, uid, at, goals, assists, rating, clean_sheet=opp == 0, line=line)


def _local_day(schedule: list[str], index: int) -> Optional[date]:
    if index >= len(schedule):
        return None
    return ensure_aware(datetime.fromisoformat(schedule[index])).astimezone(app_timezone()).date()


async def _daily_digest(db: AsyncSession, league: ManagerLeague, per_day: int) -> None:
    """One evening summary for every owner instead of a message per match."""
    state = league.state
    teams = state["teams"]
    table = standings(state)
    place_of = {row["team_index"]: n for n, row in enumerate(table, start=1)}
    today = state["results"][-per_day:]
    for t in teams:
        if not t["club_id"]:
            continue
        w = d = l = 0
        for results in today:
            for m in results:
                if t["index"] not in (m["home"], m["away"]):
                    continue
                own, opp = (m["hs"], m["as"]) if m["home"] == t["index"] else (m["as"], m["hs"])
                w, d, l = (w + 1, d, l) if own > opp else (w, d + 1, l) if own == opp else (w, d, l + 1)
        await notify(
            db, t["owner_id"], NotificationType.manager_event, f"«{t['name']}»: итоги дня",
            f"Сегодня {w}-{d}-{l}, {place_of[t['index']]} место после {league.rounds_played} туров",
            related_object_type=RELATED, related_object_id=t["club_id"],
        )


async def _finish(db: AsyncSession, league: ManagerLeague, config) -> None:
    state = league.state
    teams = state["teams"]
    pct = _pct(config.manager_division_income_pct, league.division)
    places = list(config.manager_place_rewards or [])
    budgets = list(config.manager_place_budget or [])
    now = datetime.now(timezone.utc)
    champion = None
    for place, row in enumerate(standings(state), start=1):
        team = teams[row["team_index"]]
        if not team["club_id"]:
            continue
        club = (await _lock_clubs(db, [team["club_id"]]))[team["club_id"]]
        coins = int(places[place - 1]) * pct // 100 if place - 1 < len(places) else 0
        budget = int(budgets[place - 1]) * pct // 100 if place - 1 < len(budgets) else 0
        if coins > 0:
            locked = await wallet_service.lock_user_for_update(db, club.owner_id)
            await wallet_service.credit_coins(
                db, locked, coins, TransactionType.manager_reward, f"«Менеджер»: {place} место с «{club.name}»",
                related_object_type=RELATED, related_object_id=club.id,
            )
        club.budget += budget
        club.seasons_played += 1
        if place == 1:
            club.titles += 1
            champion = club.name
        await _expire(db, club, now)
        prize = ", ".join(x for x in (f"+{coins} монет тебе" if coins else "", f"+{money(budget)} в бюджет" if budget else "") if x)
        await notify(
            db, club.owner_id, NotificationType.manager_event, f"Сезон окончен: {place} место",
            f"«{club.name}» — {place} место в {division_name(league.division)}" + (f" · {prize}" if prize else ""),
            related_object_type=RELATED, related_object_id=club.id,
        )
    league.state = {**state, "champion": champion}
    flag_modified(league, "state")
    league.status = "finished"
    league.finished_at = now
    await db.flush()
    still = (await db.execute(
        select(func.count(ManagerLeague.id)).where(ManagerLeague.season_key == league.season_key, ManagerLeague.status == "active")
    )).scalar_one()
    if still == 0:
        await _settle(db, league.season_key, config)


async def _settle(db: AsyncSession, key: str, config) -> None:
    """Promotion and relegation once every league of the season is over —
    one division at most per season, the pyramid kept ×2."""
    season = (await db.execute(
        select(ManagerSeason).where(ManagerSeason.key == key).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if season is None or season.settled_at is not None:
        return
    size = league_size(config)
    promote = max(1, config.manager_promote)
    leagues = (await db.execute(select(ManagerLeague).where(ManagerLeague.season_key == key))).scalars().all()
    rank: dict[int, tuple] = {}
    league_count: dict[int, int] = {}
    for lg in leagues:
        league_count[lg.division] = league_count.get(lg.division, 0) + 1
        for place, row in enumerate(standings(lg.state), start=1):
            team = lg.state["teams"][row["team_index"]]
            if team["club_id"]:
                rank[team["club_id"]] = (place, -row["points"], -(row["gf"] - row["ga"]), -row["gf"])
    clubs = await _lock_clubs(db, (await db.execute(select(ManagerClub.id))).scalars().all())
    depth = depth_of(config)
    for club in clubs.values():
        club.division = min(club.division, depth)  # the admin may have cut the pyramid
    members: dict[int, list[ManagerClub]] = {}
    for club in clubs.values():
        members.setdefault(club.division, []).append(club)
    unranked = (99, 0, 0, 0)

    def key_of(c: ManagerClub) -> tuple:
        return (*rank.get(c.id, unranked), c.id)

    moves: dict[int, int] = {}
    for d in range(1, depth):
        here = sorted(members.get(d, []), key=key_of)
        below = sorted(members.get(d + 1, []), key=key_of)
        cap = capacity(d, config)
        leagues_here = max(league_count.get(d, 0), math.ceil(len(here) / size))
        relegate = 2 * promote * leagues_here if len(here) >= cap else 0
        relegate = min(len(here), max(relegate, len(here) - cap))
        if relegate:
            for c in here[-relegate:]:
                moves[c.id] = d + 1
        vacancies = cap - (len(here) - relegate)
        candidates = [c for c in below if rank.get(c.id, unranked)[0] <= size // 2]
        for c in candidates[:max(0, vacancies)]:
            moves[c.id] = d
    now = datetime.now(timezone.utc)
    for club_id, new in moves.items():
        club = clubs[club_id]
        old = club.division
        if new == old:
            continue
        old_grant = _pick(config.manager_division_budget, old - 1)
        new_grant = _pick(config.manager_division_budget, new - 1)
        club.division = new
        if new < old:
            bonus = new_grant * config.manager_promotion_bonus_pct // 100
            club.budget += bonus
            club.best_division = min(club.best_division or new, new)
            title, text = "повышение ⬆️", f"Теперь {division_name(new)}. Бонус {money(bonus)} в бюджет"
        else:
            parachute = max(0, old_grant - new_grant) * config.manager_parachute_pct // 100
            club.budget += parachute
            title, text = "вылет ⬇️", f"Теперь {division_name(new)}. Компенсация {money(parachute)}"
        await notify(db, club.owner_id, NotificationType.manager_event, f"«{club.name}»: {title}",
                     text, related_object_type=RELATED, related_object_id=club.id)
    season.depth = depth
    season.settled_at = now


async def resolve_league(db: AsyncSession, league_id: int, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    league = await _lock_league(db, league_id)
    played = 0
    schedule = (league.state or {}).get("schedule") or []
    total = len((league.state or {}).get("fixtures") or [])
    while league.status == "active" and league.rounds_played < min(total, len(schedule)):
        if ensure_aware(datetime.fromisoformat(schedule[league.rounds_played])) > now:
            break
        await _play_round(db, league, league.rounds_played, config)
        played += 1
    await db.commit()
    return played


async def resolve_all_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """The season start and every due round (the bot's manager sweep)."""
    await ensure_season(db, now)
    ids = (await db.execute(select(ManagerLeague.id).where(ManagerLeague.status == "active"))).scalars().all()
    return sum([await resolve_league(db, league_id, now) for league_id in ids])


# --- view -----------------------------------------------------------------------------------

def _contract_out(c: ManagerContract, mps: dict, users: dict, clubs: dict, config,
                  basis: Optional[ManagerContract] = None) -> dict:
    """`basis` = the contract whose form sets the value (an offer for a
    player of another club is valued by his current contract)."""
    mp = mps.get(c.user_id)
    club = clubs.get(c.club_id)
    rating = my_player_service.rating_of(mp, config) if mp else None
    return {
        "id": c.id, "user_id": c.user_id, "kind": c.kind, "status": c.status, "fee": c.fee, "wage": c.wage,
        "wage_eur": wage_eur(c.wage, config),
        "seasons_total": c.seasons_total, "seasons_left": c.seasons_left, "club_agreed": c.club_agreed,
        "player_agreed": c.player_agreed,
        "matches_played": c.matches_played, "goals": c.goals, "assists": c.assists, "earned": c.earned,
        "player_name": mp.name if mp else "Игрок", "owner_name": _name(users.get(c.user_id)),
        "position": mp.position.value if mp else None, "rating": rating,
        "value": live_value(rating, basis or c, config) if rating else None,
        "club_name": club.name if club else None, "club_owner": _name(users.get(club.owner_id)) if club else None,
    }


async def next_match(db: AsyncSession, league: ManagerLeague, club: ManagerClub, config) -> Optional[dict]:
    """The club's next opponent with both styles and who has the edge."""
    state = league.state or {}
    teams = state.get("teams") or []
    if league.status != "active" or league.rounds_played >= len(state.get("fixtures") or []):
        return None
    mine = next((t for t in teams if t["club_id"] == club.id), None)
    if mine is None:
        return None
    pair = next(((h, a) for h, a in state["fixtures"][league.rounds_played] if mine["index"] in (h, a)), None)
    if pair is None:
        return None
    other = teams[pair[1] if pair[0] == mine["index"] else pair[0]]
    if other["club_id"]:
        rival = await db.get(ManagerClub, other["club_id"])
        style, formation = tactics.clean_style(rival.style), tactics.clean_formation(rival.formation)
    else:
        style, formation = tactics.clean_style(other.get("style")), other.get("formation") or DEFAULT_FORMATION
    my_style = tactics.clean_style(club.style)
    schedule = state.get("schedule") or []
    return {
        "opponent": other["name"], "owner_name": other.get("owner_name"), "rating": other.get("rating"),
        "home": pair[0] == mine["index"], "at": schedule[league.rounds_played] if league.rounds_played < len(schedule) else None,
        "style": style, "formation": formation, "edge": tactics.edge(my_style, style),
        "mods": tactics.modifiers(my_style, club.formation, style, config),
    }


def zone_of(place: int, division: int, depth: int, config) -> Optional[str]:
    size = league_size(config)
    promote = max(1, config.manager_promote)
    if division > 1 and place <= promote:
        return "up"
    if division < depth and place > size - 2 * promote:
        return "down"
    return None


def _league_out(league: ManagerLeague, my_club_ids: set[int], depth: int, config) -> dict:
    state = league.state or {}
    teams = state.get("teams") or []
    schedule = state.get("schedule") or []
    results = state.get("results") or []
    rounds = []
    for r, fixtures in enumerate(state.get("fixtures") or []):
        played = results[r] if r < len(results) else None
        matches = []
        for h, a in fixtures:
            m = next((x for x in played or [] if x["home"] == h), None)
            matches.append({
                "home": teams[h]["name"], "away": teams[a]["name"],
                "mine": bool({teams[h]["club_id"], teams[a]["club_id"]} & my_club_ids),
                "live": bool(teams[h]["club_id"] and teams[a]["club_id"]),
                **({"hs": m["hs"], "away_score": m["as"],
                    "goals": [{**g, "home": g["team"] == "a"} for g in m.get("goals") or []],
                    "styles": m.get("styles"), "formations": m.get("formations")} if m else {}),
            })
        rounds.append({"index": r, "at": schedule[r] if r < len(schedule) else None, "matches": matches})
    players = state.get("players") or {}
    table = standings(state)
    total = len(state.get("fixtures") or [])
    return {
        "id": league.id, "season_key": league.season_key, "division": league.division, "division_name": division_name(league.division),
        "status": league.status, "rounds_played": league.rounds_played, "total_rounds": total,
        "next_round_at": schedule[league.rounds_played] if league.status == "active" and league.rounds_played < len(schedule) else None,
        "table": [
            {**row, "name": teams[row["team_index"]]["name"], "owner_name": teams[row["team_index"]]["owner_name"],
             "club_id": teams[row["team_index"]]["club_id"],
             "is_mine": teams[row["team_index"]]["club_id"] in my_club_ids, "is_live": bool(teams[row["team_index"]]["club_id"]),
             "zone": zone_of(i + 1, league.division, depth, config)}
            for i, row in enumerate(table)
        ],
        "rounds": rounds,
        "players": sorted(
            ({"name": p["name"], "team": teams[p["team_index"]]["name"], "matches": p["matches"], "goals": p["goals"],
              "assists": p["assists"], "avg_rating": round(p["rating_sum"] / p["matches"], 2) if p["matches"] else None}
             for p in players.values()),
            key=lambda p: (-p["goals"], -p["assists"], p["name"]),
        ),
        "champion": state.get("champion"),
    }


async def pyramid(db: AsyncSession, config) -> list[dict]:
    counts = dict((await db.execute(select(ManagerClub.division, func.count(ManagerClub.id)).group_by(ManagerClub.division))).all())
    depth = depth_of(config)
    return [
        {"division": d, "name": division_name(d), "clubs": int(counts.get(d, 0)), "capacity": capacity(d, config) if d < depth else None,
         "grant": _pick(config.manager_division_budget, d - 1), "rating": _division_rating(d, config)}
        for d in range(1, depth + 1)
    ]


async def get_view(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    from app.services import manager_shop

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    await ensure_season(db, now)
    club = await _owned_club(db, user.id)
    contract = await _active_contract(db, user.id)
    playing_club = await db.get(ManagerClub, contract.club_id) if contract else None
    for c in (club, playing_club):
        if c is not None and c.league_id and await is_playing(db, c):
            await resolve_league(db, c.league_id, now)
    key = season_key(now)
    if club is not None:
        club = await _owned_club(db, user.id, lock=True)
        if club.budget_season != key and not await is_playing(db, club):
            await _grant_budget(db, club, key, config)
        await db.commit()
        club = await _owned_club(db, user.id)
    contract = await _active_contract(db, user.id)
    playing_club = await db.get(ManagerClub, contract.club_id) if contract else None
    mp = await my_player_service.get_my_player(db, user.id)

    offers_to_me = list((await db.execute(
        select(ManagerContract).where(ManagerContract.user_id == user.id, ManagerContract.status == "offered")
        .order_by(ManagerContract.id.desc())
    )).scalars().all())
    club_contracts = await _contracts(db, club.id, ("active", "offered", "on_loan")) if club else []
    incoming = []
    if club is not None:
        mine_ids = [c.id for c in club_contracts if c.status == "active"]
        incoming = list((await db.execute(
            select(ManagerContract).where(ManagerContract.from_contract_id.in_(mine_ids or [0]), ManagerContract.status == "offered")
        )).scalars().all())
    parents = {c.id: c for c in club_contracts}
    all_contracts = [*offers_to_me, *club_contracts, *incoming, *([contract] if contract else [])]
    clubs = {c.id: c for c in (await db.execute(
        select(ManagerClub).where(ManagerClub.id.in_({c.club_id for c in all_contracts} | ({club.id} if club else set()) or {0}))
    )).scalars().all()}
    ids = {user.id, *(c.user_id for c in all_contracts), *(c.owner_id for c in clubs.values())}
    users = await _users(db, ids)
    mps = await _my_players(db, ids)
    levels = await pyramid(db, config)
    depth = len(levels)

    club_out = None
    if club is not None:
        playing = await is_playing(db, club)
        squad = await squad_view(db, club, config)
        npcs = await _npcs(db, club.id)
        players = {p.id: p for p in (await db.execute(select(Player).where(Player.id.in_({n.player_id for n in npcs} or {0})))).scalars().all()}
        snap = await base_snapshot(db, club.owner_id, config)
        academy = await academy_options(db, club.owner_id)
        grant = season_grant(club.division, snap, config)
        wage_pct = _pct(config.manager_division_wage_pct, club.division)
        club_out = {
            "id": club.id, "name": club.name, "formation": tactics.clean_formation(club.formation),
            "style": tactics.clean_style(club.style), "budget": club.budget,
            "division": club.division, "division_name": division_name(club.division), "playing": playing,
            "seasons_played": club.seasons_played, "titles": club.titles, "best_division": club.best_division,
            "base": snap, "next_grant": grant, "ticket_per_home_match": ticket_income(club.division, snap, config),
            "squad": squad,
            "contracts": [_contract_out(c, mps, users, clubs, config) for c in club_contracts if c.status in ("active", "on_loan")],
            "offers_sent": [_contract_out(c, mps, users, clubs, config) for c in club_contracts if c.status == "offered"],
            "incoming": [_contract_out(c, mps, users, clubs, config, basis=parents.get(c.from_contract_id)) for c in incoming],
            "npcs": [
                {"id": n.id, "player_id": n.player_id, "name": players[n.player_id].display_name, "position": players[n.player_id].position.value,
                 "rating": players[n.player_id].rating, "kind": n.kind, "auto": n.auto, "seasons_left": n.seasons_left,
                 "wage": n.wage * wage_pct // 100 * (100 - snap["discount_pct"]) // 100, "goals": n.goals,
                 **{k: v for k, v in npc_terms(players[n.player_id].rating, config).items() if k in ("value", "sell_back")}}
                for n in npcs if n.player_id in players
            ],
            "wages_per_season": sum(wage_eur(min(c.wage, config.manager_live_wage_max), config) for c in club_contracts if c.status == "active")
            + sum(n.wage * wage_pct // 100 * (100 - snap["discount_pct"]) // 100 for n in npcs),
            "squad_value": sum(p.get("value", 0) for p in (*squad["xi"], *squad["bench"])), "next_match": None,
            "live_count": sum(1 for c in club_contracts if c.status in ("active", "offered") and c.user_id != club.owner_id),
            "academy_card_id": club.academy_card_id,
            "academy_options": [
                {"card_id": c.id, "name": c.player.display_name, "position": c.player.position.value, "rating": _card_rating(c, config)}
                for c in academy
            ],
            **(await manager_shop.club_style(db, club, config, now)),
        }
    league = None
    league_club = club if club is not None and club.league_id else playing_club if playing_club is not None and playing_club.league_id else None
    if league_club is not None:
        row = await db.get(ManagerLeague, league_club.league_id)
        if row is not None:
            league = _league_out(row, {x.id for x in (club, playing_club) if x is not None}, depth, config)
            if club_out is not None and league_club is club:
                club_out["next_match"] = await next_match(db, row, club, config)
    pre_end = preseason_end(now, config)
    started = await db.get(ManagerSeason, season_key(now)) is not None
    next_pre_end = pre_end if now < pre_end else preseason_end(week_start(now) + timedelta(days=7), config)
    my_rating = my_player_service.rating_of(mp, config) if mp else None
    my_value = live_value(my_rating, contract, config) if mp else None
    my_trend = (await value_trends(db, [user.id], {user.id: my_value}))[user.id] if mp else None
    return {
        "enabled": bool(config.manager_enabled),
        "has_player": mp is not None,
        "balance": user.balance,
        "level": _level(user, config),
        "market_open": bool(mp and mp.market_open),
        "my_value": my_value, "my_rating": my_rating, "my_trend_pct": my_trend,
        "season": {
            "key": season_key(now), "phase": "season" if started else "preseason",
            "preseason_ends_at": next_pre_end.astimezone(timezone.utc).isoformat(),
            "first_round_at": season_schedule(next_pre_end, config)[0],
            "slots": [f"{h:02d}:{m:02d}" for h, m in slots_of(config)], "rounds": rounds_of(config),
        },
        "pyramid": levels,
        "rules": {
            "found_cost": config.manager_found_cost, "min_level": config.manager_min_level,
            "max_live": config.manager_max_live, "squad_max": config.manager_squad_max,
            "live_wage_max": config.manager_live_wage_max, "wage_eur_per_coin": config.manager_wage_eur_per_coin,
            "contract_seasons": list(CONTRACT_SEASONS), "league_size": league_size(config), "promote": max(1, config.manager_promote),
            "place_rewards": list(config.manager_place_rewards or []), "place_budget": list(config.manager_place_budget or []),
            "rounds": rounds_of(config), "divisions": max(1, config.manager_divisions),
            "promotion_bonus_pct": config.manager_promotion_bonus_pct, "parachute_pct": config.manager_parachute_pct,
            "tactics": tactics.rules_out(config),
        },
        "club": club_out,
        "contract": _contract_out(contract, mps, users, clubs, config) if contract else None,
        "offers": [_contract_out(o, mps, users, clubs, config) for o in offers_to_me],
        "league": league,
        "shop": await manager_shop.shop_out(db, user, club, config),
    }
