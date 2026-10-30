"""Карьера тренера: weekly 8-team league, 14 rounds (double round-robin),
two rounds a day at CAREER_SLOTS. Humans field their own cards (a 16-card
squad picked at the start); the other teams are bots built from real
players, tuned to the human squad and the chosen difficulty.

Rounds are resolved lazily (whenever a participant opens the career screen)
and by the bot's scheduler hitting /internal/career/resolve-due at the slot
times — both go through `resolve_due`, which locks the season row, so a
round is never played twice. Matches use the player-tournament engine
(tournament_match_engine + club_tactical_matchup_service), including card
skills. All economy numbers come from GameConfig.career_*.
"""
import contextlib
import copy
import random
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.card import UserCard
from app.models.career import CareerClub, CareerParticipant, CareerProfile, CareerSeason, Friendship
from app.models.enums import NotificationType, Position, Rarity, TransactionType
from app.models.player import Player
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import career_achievements_service as achievements
from app.services import career_league_service as league_service
from app.services import career_replay_service as career_replay
from app.services import career_tactics_service as tactics
from app.services import chemistry_service
from app.services import club_base_service, my_player_service, path_match_service, tournament_match_engine, wallet_service
from app.services.auto_squad_service import SlotSpec, owned_cards, pick_cards
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES, build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, on_ideal_position
from app.services.notification_service import notify
from app.services.player_stats_service import card_rating_bonus
from app.services.player_tournament_simulation_service import _EngineCard, _engine_card
from app.services.player_identity import card_person

TEAMS = 8
ROUNDS = 14
SQUAD_SIZE = 16  # seasons from before GameConfig.career_squad_size
# Local times of the two daily rounds. Keep in sync with bot/services/career_scheduler.py.
# 12:00 and 19:00 avoid the club (20:00) and player-tournament (10/15/21) slots.
CAREER_SLOTS: tuple[tuple[int, int], ...] = ((12, 0), (19, 0))
START_LEAD = timedelta(hours=1)  # time to set a lineup before round 1
INVITE_TTL = timedelta(hours=24)
DIFFICULTIES = ("amateur", "pro", "legend")
DIFFICULTY_LABELS = {"amateur": "Любитель", "pro": "Профи", "legend": "Легенда"}
BOT_FORMATIONS = ("4-3-3", "4-4-2", "3-5-2", "4-3-3H", "4-2-3-1", "3-4-3")
BOT_CLUB_NAMES = [
    "Северный Ветер", "Портовые Волки", "Динамо Рассвет", "Торпедо Восток", "Атлетик Лесной",
    "Горняк", "Спартак Заречье", "Метеор", "Звезда Юга", "Речники", "Сокол", "Буревестник",
]
ACTIVE_STATUSES = ("pending", "active")
# Default names for the GameConfig.career_division_count = 5 ladder (1 = top).
DIVISION_NAMES = ("Высшая лига", "Первая лига", "Вторая лига", "Третья лига", "Любительская лига")


# --- divisions -----------------------------------------------------------------

def division_count(config) -> int:
    return max(1, int(config.career_division_count or 1))


def division_name(division: int, config) -> str:
    count = division_count(config)
    if count == len(DIVISION_NAMES):
        return DIVISION_NAMES[division - 1]
    if division == 1:
        return DIVISION_NAMES[0]
    return DIVISION_NAMES[-1] if division == count else f"Дивизион {division}"


def _division_setting(config, field: str, division: int, default):
    values = list(getattr(config, field) or [])
    return values[division - 1] if 0 < division <= len(values) else default


def division_bot_level(division: int, config) -> str:
    level = _division_setting(config, "career_division_bot_level", division, "pro")
    return level if level in DIFFICULTIES else "pro"


def division_after(division: int, place: int, config) -> int:
    """Where `place` in a `division` league sends the team next season."""
    count = division_count(config)
    if place <= int(config.career_division_promote):
        division -= 1
    elif place > TEAMS - int(config.career_division_relegate):
        division += 1
    return max(1, min(count, division))


async def _legacy_division(db: AsyncSession, user_id: int, config) -> int:
    """Division for a user without a profile yet: where their last finished
    (or left) season sent them; newcomers start at the bottom."""
    last = (await db.execute(
        select(CareerParticipant.next_division)
        .where(CareerParticipant.user_id == user_id, CareerParticipant.next_division.is_not(None))
        .order_by(CareerParticipant.id.desc()).limit(1)
    )).scalar_one_or_none()
    count = division_count(config)
    return max(1, min(count, last if last is not None else count))


async def get_profile(db: AsyncSession, user_id: int, config) -> CareerProfile:
    profile = (await db.execute(select(CareerProfile).where(CareerProfile.user_id == user_id))).scalar_one_or_none()
    if profile is None:
        profile = CareerProfile(user_id=user_id, division=await _legacy_division(db, user_id, config),
                                reputation=0, tenure={}, league={})
        db.add(profile)
        await db.flush()
    return profile


async def current_division(db: AsyncSession, user_id: int, config) -> int:
    """The division the user's next season is played in (career profile)."""
    profile = await get_profile(db, user_id, config)
    return max(1, min(division_count(config), profile.division))


# --- board objectives & reputation -------------------------------------------------

AMBITIONS = ("survive", "mid", "promote")
DEFAULT_AMBITION = "mid"
REP_LEVEL_NAMES = ("Новичок", "Подающий надежды", "Опытный тренер", "Известный тренер", "Легенда")


def ambition_target(ambition: str, division: int, config) -> dict:
    """What the board expects: the worst acceptable place and its wording."""
    count = division_count(config)
    relegate, promote = int(config.career_division_relegate), int(config.career_division_promote)
    if ambition == "promote":
        if division == 1:
            return {"place": 1, "label": "Чемпионство", "text": "выиграть высшую лигу"}
        return {"place": max(1, promote), "label": "Выход наверх", "text": f"финишировать в топ-{max(1, promote)}"}
    if ambition == "mid":
        return {"place": 5, "label": "Середина таблицы", "text": "финишировать в топ-5"}
    safe = TEAMS - relegate if division < count and relegate else TEAMS - 2
    return {"place": safe, "label": "Выживание", "text": f"не опуститься ниже {safe}-го места"}


def ambition_options(division: int, config) -> list[dict]:
    bonus = list(config.career_ambition_bonus_pct or [0, 0, 0])
    good = list(config.career_ambition_rep_success or [0, 0, 0])
    bad = list(config.career_ambition_rep_fail or [0, 0, 0])
    return [{"code": a, **ambition_target(a, division, config), "bonus_pct": int(bonus[i]),
             "rep_success": int(good[i]), "rep_fail": int(bad[i])} for i, a in enumerate(AMBITIONS)]


def reputation_level(reputation: int, config) -> dict:
    levels = sorted(int(x) for x in (config.career_rep_levels or [0]))
    index = max(i for i, threshold in enumerate(levels) if reputation >= threshold) if reputation >= levels[0] else 0
    name = REP_LEVEL_NAMES[min(index, len(REP_LEVEL_NAMES) - 1)]
    nxt = levels[index + 1] if index + 1 < len(levels) else None
    return {"level": index + 1, "name": name, "next_at": nxt, "floor": levels[index]}


def _profile_out(profile: CareerProfile, config) -> dict:
    return {
        "division": profile.division, "reputation": profile.reputation, **{f"rep_{k}": v for k, v in reputation_level(profile.reputation, config).items()},
        "seasons_played": profile.seasons_played, "titles": profile.titles, "promotions": profile.promotions,
        "objectives_met": profile.objectives_met,
        "achievements": achievements.achievements_out(profile),
    }


# --- training before a round ----------------------------------------------------------

TRAININGS = {
    "recovery": ("Восстановление", "Лёгкие занятия: усталость всей заявки ниже к матчу."),
    "tactical": ("Тактика", "Отработка схемы: сыгранность в этом матче выше. Нагрузка — немного усталости."),
    "opponent": ("Разбор соперника", "Взаимодействия в вашу пользу в этом матче сильнее. Нагрузка — немного усталости."),
    "set_pieces": ("Стандарты", "Угловые и штрафные в этом матче опаснее. Нагрузка — немного усталости."),
}


def training_options() -> list[dict]:
    return [{"code": code, "label": label, "hint": hint} for code, (label, hint) in TRAININGS.items()]


async def set_ambition(db: AsyncSession, user: User, ambition: str) -> None:
    """Board objective: chosen before round 1 (fixed once the season is on)."""
    if ambition not in AMBITIONS:
        raise ConflictError("Неизвестная цель")
    part = await _editable_participation(db, user, None)
    season = await db.get(CareerSeason, part.season_id)
    if season.division is None:
        raise ConflictError("Задачи руководства — с нового сезона")
    if season.rounds_played > 0:
        raise ConflictError("Цель на сезон уже не изменить — первый тур сыгран")
    part.ambition = ambition
    await db.commit()


async def set_training(db: AsyncSession, user: User, training: Optional[str], round_index: Optional[int] = None) -> None:
    if training is not None and training not in TRAININGS:
        raise ConflictError("Неизвестная тренировка")
    part = await _editable_participation(db, user, round_index)
    season = await db.get(CareerSeason, part.season_id)
    if _tactics_version(season.state) < tactics.TACTICS_VERSION:
        raise ConflictError("Тренировки — с нового сезона")
    part.training = training
    await db.commit()


def _division_info(division: int, config) -> dict:
    level = division_bot_level(division, config)
    return {
        "division": division, "name": division_name(division, config), "count": division_count(config),
        "reward_pct": int(_division_setting(config, "career_division_reward_pct", division, 100)),
        "bot_level": level, "bot_level_label": DIFFICULTY_LABELS[level],
        "promote": int(config.career_division_promote), "relegate": int(config.career_division_relegate),
    }


# --- schedule & fixtures -----------------------------------------------------

def build_schedule(now: datetime) -> list[str]:
    """14 consecutive CAREER_SLOTS starting at the first one at least
    START_LEAD from now (UTC ISO strings)."""
    tz = app_timezone()
    local = ensure_aware(now).astimezone(tz)
    earliest = local + START_LEAD
    times: list[datetime] = []
    day = local.date()
    while len(times) < ROUNDS:
        for hour, minute in CAREER_SLOTS:
            at = datetime.combine(day, time(hour, minute), tzinfo=tz)
            if at >= earliest and len(times) < ROUNDS:
                times.append(at)
        day += timedelta(days=1)
    return [t.astimezone(timezone.utc).isoformat() for t in times]


def double_round_robin(teams: int = TEAMS) -> list[list[list[int]]]:
    """Circle method: every team meets every other once in rounds 1-7 and
    again with home/away swapped in rounds 8-14."""
    order = list(range(teams))
    first_half: list[list[list[int]]] = []
    for r in range(teams - 1):
        pairs = []
        for i in range(teams // 2):
            a, b = order[i], order[teams - 1 - i]
            pairs.append([a, b] if (r + i) % 2 == 0 else [b, a])
        first_half.append(pairs)
        order = [order[0], order[-1], *order[1:-1]]
    return first_half + [[[b, a] for a, b in pairs] for pairs in first_half]


def _todays_slot_times() -> list[datetime]:
    tz = app_timezone()
    today = datetime.now(tz).date()
    return [datetime.combine(today, time(h, m), tzinfo=tz) for h, m in CAREER_SLOTS]


def _round_at(season: CareerSeason, index: int) -> Optional[datetime]:
    schedule = (season.state or {}).get("schedule") or []
    return datetime.fromisoformat(schedule[index]) if index < len(schedule) else None


# --- squads ------------------------------------------------------------------

def _effective(card: UserCard) -> int:
    return min(99, card.player.rating + card_rating_bonus(card))


def _usable(card: UserCard) -> bool:
    return not card.is_locked_by_admin and not card.is_locked_in_trade


async def _career_cards(db: AsyncSession, user_id: int, config=None) -> list:
    """Own cards plus «Мой игрок» (a duck-typed stand-in card, if created)."""
    # Every squad the user has in a career keeps its exact copies.
    squads = (await db.execute(
        select(CareerParticipant.squad_card_ids).where(CareerParticipant.user_id == user_id)
    )).scalars().all()
    cards: list = await owned_cards(db, user_id, include={i for ids in squads for i in (ids or [])})
    mine = await my_player_service.engine_card(db, user_id, config)
    if mine is not None:
        cards.append(mine)
    return cards


def _squad_ids(part: CareerParticipant, cards_by_id: dict) -> list[int]:
    """The squad plus «Мой игрок», who is always in it (also for seasons
    started before the player was created)."""
    ids = list(part.squad_card_ids)
    mine = my_player_service.card_id_for(part.user_id)
    if mine in cards_by_id and mine not in ids:
        ids.append(mine)
    return ids


def pick_squad(cards: list[UserCard], formation: str = "4-3-3", size: int = SQUAD_SIZE) -> list[int]:
    """Best XI for the formation plus a 5-card bench (one per line + the best
    remaining), distinct players only."""
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in get_formation_slots(formation)]
    xi = pick_cards(slots, cards, "tournament")
    if len(xi) < len(slots):
        raise ConflictError("Для карьеры нужно минимум 11 карточек, закрывающих все позиции схемы 4-3-3")
    chosen = [c.id for c in xi.values()]
    used_players = {card_person(c) for c in xi.values()}
    pool = sorted(
        (c for c in cards if _usable(c) and c.id not in chosen and card_person(c) not in used_players),
        key=lambda c: (-_effective(c), c.id),
    )
    # Bench: a backup per line first (keeper, then outfield lines twice),
    # then the best of the rest.
    needs = ["GK", "DEF", "MID", "FWD", "DEF", "MID", "FWD"] + [None] * max(0, size)
    for need in needs:
        if len(chosen) >= size:
            break
        for card in pool:
            if card_person(card) in used_players:
                continue
            if need is None or card.player.position in CATEGORY_POSITIONS[need]:
                chosen.append(card.id)
                used_players.add(card_person(card))
                break
    return chosen[:size]


_FRESH = {"fatigue": 0, "injured_until": 0, "suspended_until": 0, "yellows": 0, "form": 0}


def _condition(part: CareerParticipant, card_id: int) -> dict:
    return {**_FRESH, **(part.condition or {}).get(str(card_id), {})}


def _is_out(part: CareerParticipant, card_id: int, round_index: int) -> bool:
    """Injured or suspended for `round_index`."""
    cond = _condition(part, card_id)
    return cond["injured_until"] > round_index or cond["suspended_until"] > round_index


def resolve_lineup(
    part: CareerParticipant, cards_by_id: dict[int, UserCard], round_index: int, extra_cards: list[UserCard],
    fill_any_position: bool = False, rotate: bool = False,
) -> list[tuple[UserCard, object]]:
    """The XI that plays `round_index`: the saved lineup where its cards are
    still owned, fit and in a legal slot, the gaps auto-filled from the
    squad (fresh players first), then — if the squad can't cover a slot —
    from the rest of the player's own collection."""
    slots = get_formation_slots(part.formation)
    squad_ids = _squad_ids(part, cards_by_id)
    squad = [cards_by_id[cid] for cid in squad_ids if cid in cards_by_id]
    available = [c for c in squad if _usable(c) and not _is_out(part, c.id, round_index)]
    by_id = {c.id: c for c in available}
    chosen: dict[str, UserCard] = {}
    used_players: set[str] = set()
    for slot in ([] if rotate else slots):  # rotation: ignore the saved XI
        card = by_id.get((part.lineup or {}).get(slot.code) or -1)
        if card and card.player.position in CATEGORY_POSITIONS[slot.category] and card_person(card) not in used_players:
            chosen[slot.code] = card
            used_players.add(card_person(card))
    missing = [SlotSpec(s.code, s.category, s.ideal_position) for s in slots if s.code not in chosen]
    if missing:
        fresh = frozenset(c.id for c in available if _condition(part, c.id).get("fatigue", 0) < (35 if rotate else 60))
        pool = [c for c in available if card_person(c) not in used_players]
        for code, card in pick_cards(missing, pool, "tournament", preferred_ids=fresh).items():
            chosen[code] = card
            used_players.add(card_person(card))
    missing = [SlotSpec(s.code, s.category, s.ideal_position) for s in slots if s.code not in chosen]
    if missing:
        pool = [c for c in extra_cards if card_person(c) not in used_players and c.id not in squad_ids]
        for code, card in pick_cards(missing, pool, "tournament").items():
            chosen[code] = card
            used_players.add(card_person(card))
    if fill_any_position:
        # Still a hole (nobody of that line is fit or owned): rather than a
        # technical defeat, the best remaining fit player plays out of
        # position — squad first, then the collection; outfield before a
        # keeper and vice versa.
        for slot in slots:
            if slot.code in chosen:
                continue
            spare = [c for c in available + [c for c in extra_cards if c.id not in squad_ids]
                     if card_person(c) not in used_players]
            if not spare:
                break
            prefer_gk = slot.category == "GK"
            card = max(spare, key=lambda c: ((c.player.position.value == "GK") == prefer_gk, _effective(c), -c.id))
            chosen[slot.code] = card
            used_players.add(card_person(card))
    return [(chosen[s.code], s) for s in slots if s.code in chosen]


# --- engine sides ------------------------------------------------------------

def _human_side(part: CareerParticipant, pairs: list, config):
    if len(pairs) != len(get_formation_slots(part.formation)):
        return None
    with_slots = []
    for card, slot in pairs:
        engine_card = _engine_card(card, config)
        cond = _condition(part, card.id)
        penalty = cond["fatigue"] / 100 * config.career_fatigue_penalty_pct / 100
        # Form from the previous match: +up to career_form_max / -1 rating.
        rating = engine_card.player.rating * (1 - penalty) + cond["form"]
        engine_card.player.rating = max(1, min(99, round(rating)))
        with_slots.append((engine_card, slot))
    side = build_side(with_slots, part.mentality, part.playstyle)
    lineup = [
        {
            "club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name,
            "rating": c.player.rating, "position": c.player.position.value, "category": slot.category,
            **({"skill": c.skill} if c.skill else {}),
            **({"boosts": c.boosts} if getattr(c, "boosts", None) else {}),
        }
        for c, slot in with_slots
    ]
    return side, lineup


def _bot_cards(team: dict, round_index: int, config) -> list:
    slots = {s.code: s for s in get_formation_slots(team["formation"])}
    growth = config.career_bot_growth_tenths * round_index / 10
    with_slots = []
    for i, p in enumerate(team["players"]):
        player = SimpleNamespace(
            display_name=p["name"], position=Position(p["position"]), rating=min(99, round(p["rating"] + growth)),
            rarity=Rarity(p["rarity"]), club=p["club"], country=p["country"], attack_rating=None, defense_rating=None,
        )
        with_slots.append((_EngineCard(id=-(team["index"] * 100 + i + 1), player_id=p["player_id"], player=player), slots[p["slot"]]))
    return with_slots


def _bot_side(team: dict, round_index: int, config):
    with_slots = _bot_cards(team, round_index, config)
    side = build_side(with_slots, team["mentality"], team["playstyle"])
    lineup = [
        {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category}
        for c, slot in with_slots
    ]
    return side, lineup


async def _build_bots(
    db: AsyncSession, season: CareerSeason, bot_indexes: list[int], human_avg: float, config,
    name_pool: Optional[list[str]] = None, seed_salt: int = 0, spreads: Optional[list[int]] = None,
    clubs: Optional[list] = None,
) -> list[dict]:
    """Bot teams around the humans' strength. With `clubs` (catalog
    CareerClub rows, living league) each team is that club: its name, its
    real players first (pool_club), its formation / tactic / strength offset."""
    rng = random.Random(season.id * 7919 + seed_salt * 104729)
    if season.division is not None:
        offset = int(_division_setting(config, "career_division_rating_offset", season.division, 0))
    else:  # season from before divisions: the hand-picked difficulty
        offsets = config.career_difficulty_rating_offset or [-6, 0, 4]
        offset = offsets[DIFFICULTIES.index(season.difficulty)] if len(offsets) == 3 else 0
    spreads = list(spreads or [-4, -3, -1, 0, 1, 3, 4])
    rng.shuffle(spreads)
    names = [c.name for c in clubs] if clubs else rng.sample(name_pool or BOT_CLUB_NAMES, len(bot_indexes))
    players = (await db.execute(
        select(Player).where(Player.is_active.is_(True)).order_by(Player.id).limit(2000)
    )).scalars().all()
    by_category: dict[str, list[Player]] = {cat: [p for p in players if p.position in pos] for cat, pos in CATEGORY_POSITIONS.items()}
    teams = []
    for n, index in enumerate(bot_indexes):
        club = clubs[n] if clubs and n < len(clubs) else None
        formation = club.formation if club and club.formation in CLUB_FORMATIONS else rng.choice(BOT_FORMATIONS)
        target = human_avg + offset + spreads[n % len(spreads)] + (club.rating_offset if club else 0)
        own = [p for p in players if club and club.pool_club and (p.club or "").strip() == club.pool_club]
        used: set[int] = set()
        roster = []
        for slot in get_formation_slots(formation):
            own_fit = [p for p in own if p.id not in used and p.position in CATEGORY_POSITIONS[slot.category]]
            candidates = own_fit or [p for p in by_category[slot.category] if p.id not in used] or players
            ideal = [p for p in candidates if on_ideal_position(p.position, slot.ideal_position)]
            pick = rng.choice(ideal or candidates) if candidates else None
            if pick is not None:
                used.add(pick.id)
            roster.append({
                "slot": slot.code,
                "player_id": pick.id if pick else 0,
                "name": pick.display_name if pick else f"Игрок {len(roster) + 1}",
                "position": (pick.position if pick and pick.position in CATEGORY_POSITIONS[slot.category] else slot.ideal_position).value,
                "rarity": (pick.rarity if pick else Rarity.common).value,
                "club": pick.club if pick else names[n],
                "country": pick.country if pick else "",
                "rating": max(40, min(99, round(target + rng.uniform(-3, 3)))),
            })
        teams.append({
            "index": index, "name": names[n], "user_id": None, "formation": formation,
            "mentality": rng.choice([m for m in MENTALITIES if m != "PARK_THE_BUS"]),
            "playstyle": (preset := (club.preset if club and club.preset in tactics.PRESETS else rng.choice(PLAYSTYLES))),
            "tactic": dict(tactics.PRESETS[preset]), "players": roster, "club_id": club.id if club else None,
            "set_pieces": {**tactics.DEFAULT_SET_PIECES, "corner_routine": rng.choice(list(tactics.CORNER_ROUTINES)),
                           "corner_defence": rng.choice(list(tactics.SET_PIECE_DEFENCES))},
        })
    return teams


# --- lifecycle ---------------------------------------------------------------

def _team_name(user: User) -> str:
    return f"{user.first_name or user.username or 'Игрок'} FC"


async def _current_participation(db: AsyncSession, user_id: int) -> Optional[CareerParticipant]:
    return (await db.execute(
        select(CareerParticipant).join(CareerSeason)
        .where(
            CareerParticipant.user_id == user_id,
            CareerParticipant.status.in_(("invited", "accepted")),
            CareerSeason.status.in_(ACTIVE_STATUSES),
        )
        .order_by(CareerParticipant.id.desc()).limit(1)
    )).scalar_one_or_none()


async def _are_friends(db: AsyncSession, a: int, b: int) -> bool:
    low, high = min(a, b), max(a, b)
    return (await db.execute(
        select(Friendship.id).where(Friendship.user_low == low, Friendship.user_high == high, Friendship.status == "accepted")
    )).scalar_one_or_none() is not None


async def _activate(db: AsyncSession, season: CareerSeason, now: datetime, config) -> None:
    """Fills the empty team slots with bots, fixes the schedule and starts
    the season. Bot strength follows the humans' starting XI average."""
    humans = [p for p in season.participants if p.status == "accepted"]
    human_ratings = []
    teams: list[dict] = [None] * TEAMS  # type: ignore[list-item]
    for part in humans:
        user = await db.get(User, part.user_id)
        cards = {c.id: c for c in await _career_cards(db, part.user_id, config)}
        xi = resolve_lineup(part, cards, 0, [])
        human_ratings.extend(_effective(c) for c, _ in xi)
        teams[part.team_index] = {"index": part.team_index, "name": _team_name(user), "user_id": part.user_id}
    human_avg = sum(human_ratings) / len(human_ratings) if human_ratings else 70
    bot_indexes = [i for i in range(TEAMS) if teams[i] is None]
    clubs = None
    if season.division is not None:
        creator = await get_profile(db, season.creator_id, config)
        clubs = await league_service.league_clubs(db, creator, season.division, config, seed=season.id * 17)
    for bot in await _build_bots(db, season, bot_indexes, human_avg, config, clubs=clubs):
        teams[bot["index"]] = bot
    season.state = {
        "teams": teams, "fixtures": double_round_robin(), "schedule": build_schedule(now), "results": [],
        # Seasons without this key (started before the tactics update) keep
        # the original match path; see _play_round.
        "tactics_version": tactics.TACTICS_VERSION,
        # Chemistry rules frozen for the whole season (like player
        # tournaments): later GameConfig edits don't change a running league.
        "chemistry_rules": (rules.as_dict() if (rules := chemistry_service.active_rules(config)) else None),
    }
    if config.career_cup_enabled:
        state = dict(season.state)
        await _create_cup(db, season, state, human_avg, config)
        season.state = state
    # Every season opens with a pre-season (squad, camp, objective, a
    # friendly); _create_next_season replaces this with last season's data.
    state = dict(season.state)
    state["offseason"] = {"prev_season_id": None, "teams": {
        str(p.team_index): {"prev_squad": [], "prev_familiarity": 0, "prev_formation": None, "prev_tactic": None}
        for p in humans
    }}
    season.state = state
    season.status = "active"
    season.starts_at = datetime.fromisoformat(season.state["schedule"][0])
    season.invite_expires_at = None


async def create_season(
    db: AsyncSession, user: User, difficulty: Optional[str] = None, friend_id: Optional[int] = None,
) -> CareerSeason:
    """Starts a season in the creator's division. Difficulty is no longer
    chosen: the division sets bot strength, bot level and rewards
    (`difficulty` is accepted from old clients and ignored)."""
    config = await get_config(db)
    if not config.career_enabled:
        raise ConflictError("Карьера сейчас недоступна")
    await wallet_service.lock_user_for_update(db, user.id)  # serializes "one season at a time"
    if await _current_participation(db, user.id):
        raise ConflictError("У тебя уже идёт сезон карьеры")
    squad = pick_squad(await _career_cards(db, user.id, config), size=config.career_squad_size)

    friend: Optional[User] = None
    if friend_id is not None:
        if friend_id == user.id or not await _are_friends(db, user.id, friend_id):
            raise ForbiddenError("Пригласить можно только друга")
        friend = await db.get(User, friend_id)
        if friend is None:
            raise NotFoundError("Игрок не найден")
        if await _current_participation(db, friend_id):
            raise ConflictError("У друга уже идёт сезон карьеры")

    now = datetime.now(timezone.utc)
    division = await current_division(db, user.id, config)
    season = CareerSeason(
        difficulty=division_bot_level(division, config), division=division, creator_id=user.id, status="pending", state={},
    )
    season.participants.append(CareerParticipant(
        user_id=user.id, team_index=0, status="accepted", squad_card_ids=squad, division=division,
        ambition=DEFAULT_AMBITION,
    ))
    if friend is not None:
        season.participants.append(CareerParticipant(user_id=friend.id, team_index=1, status="invited", squad_card_ids=[]))
        season.invite_expires_at = now + INVITE_TTL
    db.add(season)
    await db.flush()
    if friend is None:
        await _activate(db, season, now, config)
    else:
        await notify(
            db, friend.id, NotificationType.career_invite, "Сезон карьеры вместе",
            f"{user.first_name or user.username or 'Друг'} зовёт тебя в общий сезон «Карьеры тренера» "
            f"({division_name(division, config)}). Ответь в течение суток.",
            related_object_type="career_season", related_object_id=season.id,
        )
    await db.commit()
    return season


async def _lock_season(db: AsyncSession, season_id: int) -> CareerSeason:
    season = (await db.execute(
        select(CareerSeason).where(CareerSeason.id == season_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if season is None:
        raise NotFoundError("Сезон не найден")
    return season


async def respond_invite(db: AsyncSession, user: User, season_id: int, accept: bool) -> CareerSeason:
    config = await get_config(db)
    season = await _lock_season(db, season_id)
    part = next((p for p in season.participants if p.user_id == user.id), None)
    if part is None or part.status != "invited" or season.status != "pending":
        raise ConflictError("Приглашение уже неактуально")
    if accept:
        if (other := await _current_participation(db, user.id)) and other.season_id != season.id:
            raise ConflictError("У тебя уже идёт другой сезон карьеры")
        part.squad_card_ids = pick_squad(await _career_cards(db, user.id, config), size=config.career_squad_size)
        part.status = "accepted"
        if season.division is not None:
            # Plays in the creator's league, moves up/down from their own.
            part.division = await current_division(db, user.id, config)
            part.ambition = DEFAULT_AMBITION
    else:
        part.status = "declined"
    await _activate(db, season, datetime.now(timezone.utc), config)
    name = user.first_name or user.username or "Друг"
    await notify(
        db, season.creator_id, NotificationType.career_invite, "Сезон карьеры начинается",
        f"{name} {'принял приглашение' if accept else 'отказался — его место займёт бот'}. Первый тур скоро.",
        related_object_type="career_season", related_object_id=season.id,
    )
    await db.commit()
    return season


async def start_without_friend(db: AsyncSession, user: User, season_id: int) -> CareerSeason:
    config = await get_config(db)
    season = await _lock_season(db, season_id)
    if season.creator_id != user.id or season.status != "pending":
        raise ConflictError("Сезон уже начался")
    for part in season.participants:
        if part.status == "invited":
            part.status = "declined"
    await _activate(db, season, datetime.now(timezone.utc), config)
    await db.commit()
    return season


async def leave_season(db: AsyncSession, user: User) -> None:
    """Quits the current season: remaining matches are technical defeats,
    no place reward. A pending season the user created is cancelled."""
    part = await _current_participation(db, user.id)
    if part is None:
        raise NotFoundError("Нет активного сезона")
    season = await _lock_season(db, part.season_id)
    if season.status == "pending" and season.creator_id == user.id:
        season.status = "cancelled"
    elif season.status == "active" and part.division is not None:
        # Leaving a running season counts as finishing last: relegation.
        config = await get_config(db)
        part.next_division = division_after(part.division, TEAMS, config)
        profile = await get_profile(db, user.id, config)
        profile.division = part.next_division
        profile.reputation = max(0, profile.reputation + int(config.career_rep_relegation))
    part.status = "left"
    await db.commit()


# --- off-season ----------------------------------------------------------------------------

CAMPS = {
    "physical": ("Физика", "Первые туры — меньше усталости за матч."),
    "tactical": ("Тактика", "Стартовая сыгранность в выбранной системе — пока её не меняешь."),
    "cohesion": ("Сплочение", "Новички не сбрасывают сыгранность ядра: она переходит даже при обновлённой заявке."),
}


def camp_options(config) -> list[dict]:
    return [{"code": code, "label": label, "hint": hint} for code, (label, hint) in CAMPS.items()]


def _offseason_of(state: dict, team_index: int) -> dict:
    """This team's off-season record: per team since friend leagues carry
    over (state["offseason"]["teams"]), the whole record before that."""
    off = state.get("offseason") or {}
    if not off:
        return {}
    teams = off.get("teams")
    if teams is None:
        return off
    mine = teams.get(str(team_index))
    return {**{k: v for k, v in off.items() if k != "teams"}, **mine} if mine else {}


def _friendly_of(state: dict, team_index: int) -> Optional[dict]:
    friendlies = state.get("friendlies")
    if friendlies is not None:
        return friendlies.get(str(team_index))
    return state.get("friendly") if team_index == 0 else None


def _offseason_familiarity(part: CareerParticipant, state: dict, config) -> None:
    """Familiarity at the start of a season that follows another: the core
    (cards kept from last season's squad) carries core_keep_pct of last
    season's familiarity if the formation is kept — with a «Сплочение» camp
    even when the core is smaller than core_min — plus the tactical camp's
    bonus."""
    off = _offseason_of(state, part.team_index)
    if not off:
        return
    core = len(set(off.get("prev_squad") or []) & set(part.squad_card_ids or []))
    part.core_count = core
    same = part.formation == off.get("prev_formation")
    carry = 0
    if same and (core >= int(config.career_core_min) or part.camp == "cohesion"):
        carry = int(off.get("prev_familiarity") or 0) * int(config.career_core_keep_pct) // 100
    part.carried_familiarity = carry
    bonus = int(config.career_camp_tactical_tenths) if part.camp == "tactical" else 0
    part.familiarity = min(int(config.career_familiarity_max_tenths), carry + bonus)
    part.familiar_formation = part.formation
    part.familiar_tactic = off.get("prev_tactic") if carry else _my_tactic(part)


def _next_squad(prev: list[int], cards: list, formation: str, size: int) -> list[int]:
    """Last season's squad (still owned and usable) topped up with the best
    remaining cards: the core stays unless the coach changes it."""
    by_id = {c.id: c for c in cards}
    kept = [cid for cid in prev if cid in by_id and _usable(by_id[cid])][:size]
    used_players = {card_person(by_id[cid]) for cid in kept}
    best = pick_squad(cards, formation if formation in CLUB_FORMATIONS else "4-3-3", size=size)
    for cid in best:
        if len(kept) >= size:
            break
        if cid not in kept and card_person(by_id[cid]) not in used_players:
            kept.append(cid)
            used_players.add(card_person(by_id[cid]))
    return kept


async def _create_next_season(
    db: AsyncSession, parts: list[CareerParticipant], prev: CareerSeason, config, now: datetime,
) -> None:
    """Right after a season ends: the next one, first round the next day.
    A coach who hasn't opened the career for career_inactive_days isn't
    renewed and drops a division instead. Two friends who played together
    keep their league when both are active and land in the same division;
    otherwise each gets a season of their own."""
    if not config.career_offseason_auto or not config.career_enabled:
        return
    cutoff = now - timedelta(days=int(config.career_inactive_days))
    ready = []
    for part in sorted(parts, key=lambda p: p.team_index):
        profile = await get_profile(db, part.user_id, config)
        if profile.last_active_at is None or ensure_aware(profile.last_active_at) < cutoff:
            profile.division = min(division_count(config), profile.division + 1)
            await notify(
                db, part.user_id, NotificationType.career_season_finished, "Карьера на паузе",
                f"Тебя давно не было — новый сезон не начат, клуб опустился в дивизион «{division_name(profile.division, config)}». "
                "Загляни в карьеру, чтобы начать снова.",
                related_object_type="career_season", related_object_id=prev.id,
            )
            continue
        if await _current_participation(db, part.user_id):
            continue
        cards = await _career_cards(db, part.user_id, config)
        try:
            squad = _next_squad(list(part.squad_card_ids or []), cards, part.formation, int(config.career_squad_size))
        except ConflictError:
            continue  # not enough cards for a team any more
        ready.append((part, profile, squad))
    together = len(ready) == 2 and ready[0][1].division == ready[1][1].division
    for group in ([ready] if together else [[r] for r in ready]):
        division = group[0][1].division
        season = CareerSeason(
            difficulty=division_bot_level(division, config), division=division, creator_id=group[0][0].user_id,
            status="pending", state={},
        )
        new_parts = []
        for team_index, (part, _profile, squad) in enumerate(group):
            lineup = {code: cid for code, cid in (part.lineup or {}).items() if cid in squad} or None
            new_part = CareerParticipant(
                user_id=part.user_id, team_index=team_index, status="accepted", squad_card_ids=squad, division=division,
                ambition=DEFAULT_AMBITION, formation=part.formation, mentality=part.mentality, playstyle=part.playstyle,
                tactic=part.tactic, set_pieces=part.set_pieces, match_plan=part.match_plan, lineup=lineup,
                training=part.training, roles=part.roles,
            )
            season.participants.append(new_part)
            new_parts.append((part, new_part))
        db.add(season)
        await db.flush()
        await _activate(db, season, now, config)
        state = dict(season.state)
        state["offseason"] = {"prev_season_id": prev.id, "teams": {
            str(new.team_index): {
                "prev_squad": list(old.squad_card_ids or []), "prev_familiarity": int(old.familiarity or 0),
                "prev_formation": old.formation, "prev_tactic": _my_tactic(old),
            }
            for old, new in new_parts
        }}
        season.state = state
        first = datetime.fromisoformat(state["schedule"][0])
        names = {p.user_id: _team_name(await db.get(User, p.user_id)) for _, p in new_parts}
        for _, new_part in new_parts:
            _offseason_familiarity(new_part, state, config)
            friend = next((names[p.user_id] for _, p in new_parts if p.user_id != new_part.user_id), None)
            await notify(
                db, new_part.user_id, NotificationType.career_invite, "Предсезонка: новый сезон уже ждёт",
                (f"Ваша лига с «{friend}» продолжается. " if friend else "")
                + f"Первый тур — {first.astimezone(app_timezone()).strftime('%d.%m в %H:%M')}. До старта можно "
                "обновить заявку, выбрать сборы и цель руководства, сыграть товарищеский матч.",
                related_object_type="career_season", related_object_id=season.id,
            )


async def _editable_offseason(db: AsyncSession, user: User) -> tuple[CareerParticipant, CareerSeason]:
    part = await _editable_participation(db, user, None)
    season = await _lock_season(db, part.season_id)
    if season.rounds_played > 0:
        raise ConflictError("Сезон уже идёт — это меняется только до первого тура")
    if _tactics_version(season.state) < tactics.TACTICS_VERSION:
        raise ConflictError("Доступно с нового сезона")
    return part, season


async def set_squad(db: AsyncSession, user: User, card_ids: list[int]) -> None:
    """The season squad (заявка), before round 1: own usable cards, distinct
    players, up to career_squad_size, covering every position of the formation."""
    config = await get_config(db)
    part, season = await _editable_offseason(db, user)
    cards = {c.id: c for c in await _career_cards(db, user.id, config)}
    if len(card_ids) > int(config.career_squad_size):
        raise ConflictError(f"В заявке не больше {config.career_squad_size} игроков")
    players: set[str] = set()
    for cid in card_ids:
        card = cards.get(cid)
        if card is None or not _usable(card):
            raise ConflictError("В заявку — только свои доступные карточки")
        if card_person(card) in players:
            raise ConflictError("Один игрок не может быть в заявке дважды")
        players.add(card_person(card))
    probe = CareerParticipant(squad_card_ids=list(card_ids), formation=part.formation, condition={}, lineup=None, user_id=user.id)
    xi = resolve_lineup(probe, cards, 0, [])
    if len(xi) < len(get_formation_slots(part.formation)):
        raise ConflictError("Заявка должна закрывать все позиции схемы")
    part.squad_card_ids = list(card_ids)
    part.lineup = {code: cid for code, cid in (part.lineup or {}).items() if cid in card_ids} or None
    _offseason_familiarity(part, season.state or {}, config)
    await db.commit()


async def set_camp(db: AsyncSession, user: User, camp: Optional[str]) -> None:
    if camp is not None and camp not in CAMPS:
        raise ConflictError("Неизвестные сборы")
    config = await get_config(db)
    part, season = await _editable_offseason(db, user)
    part.camp = camp
    _offseason_familiarity(part, season.state or {}, config)
    await db.commit()


async def play_friendly(db: AsyncSession, user: User) -> None:
    """One free friendly before round 1 against a club of the division:
    no rewards, no fatigue, no familiarity — a test of tactic and squad."""
    config = await get_config(db)
    part, season = await _editable_offseason(db, user)
    state = copy.deepcopy(season.state or {})
    if _friendly_of(state, part.team_index):
        raise ConflictError("Товарищеский матч уже сыгран")
    league_ids = {t.get("club_id") for t in state.get("teams") or []}
    pool = (await db.execute(
        select(CareerClub).where(CareerClub.division == season.division, CareerClub.is_active.is_(True))
    )).scalars().all()
    rng = random.Random(season.id * 613)
    candidates = [c for c in pool if c.id not in league_ids] or list(pool)
    cards = await _career_cards(db, user.id, config)
    me_team = state["teams"][part.team_index]
    human_avg = sum(_effective(c) for c, _ in resolve_lineup(part, {c.id: c for c in cards}, 0, [])) / 11
    bots = await _build_bots(db, season, [99], human_avg, config, clubs=[rng.choice(candidates)] if candidates else None,
                             seed_salt=7)
    bot = bots[0]
    chem_rules = chemistry_service.rules_from_dict(state.get("chemistry_rules"))
    runner, _, _ = _human_runner(part, cards, config, chem_rules, "a", me_team["name"], avail_round=0,
                                 profile=await get_profile(db, user.id, config))
    if runner is None:
        raise ConflictError("Не хватает игроков на состав")
    choice = {"tactic": tactics.tactic_for(bot.get("tactic"), bot.get("playstyle")), "familiarity": 0, "plan": None}
    other = _bot_runner(bot, "b", 0, config, chem_rules, choice)
    tracker: dict = {}
    lineups = {"a": career_replay.lineup_record(runner), "b": career_replay.lineup_record(other)}
    match = tournament_match_engine.simulate_match_controlled(
        tactics.CareerMatchController(runner, other), config, me_team["name"], bot["name"], tracker=tracker,
    )
    state.setdefault("friendlies", {})[str(part.team_index)] = {
        "opponent": bot["name"], "home_score": match.score_a, "away_score": match.score_b, "events": match.event_log,
        "analysis": tactics.build_analysis(match.event_log, tracker, "a", runner, other),
        "lineups": lineups,
    }
    season.state = state
    flag_modified(season, "state")
    await db.commit()


async def _offseason_out(db: AsyncSession, season: CareerSeason, me: CareerParticipant, config) -> Optional[dict]:
    """The off-season panel of a season created after another, until its
    first round: last season's result and summary, the core, camps, the
    friendly match."""
    state = season.state or {}
    off = _offseason_of(state, me.team_index)
    if not off or season.rounds_played > 0 or me.status != "accepted":
        return None
    prev = await db.get(CareerSeason, off["prev_season_id"]) if off.get("prev_season_id") else None
    prev_part = next((p for p in prev.participants if p.user_id == me.user_id), None) if prev else None
    cards = {c.id: c for c in await _career_cards(db, me.user_id)}
    names = {cid: c.player.display_name for cid, c in cards.items()}
    friendly = _friendly_of(state, me.team_index)
    friend = next((p for p in season.participants if p.user_id != me.user_id and p.status == "accepted"), None)
    return {
        "friend_league": friend is not None and prev is not None,
        "first_season": prev is None,
        "prev_season_id": prev.id if prev else None,
        "prev_place": prev_part.final_place if prev_part else None,
        "prev_division": _division_info(prev_part.division, config) if prev_part and prev_part.division else None,
        "prev_coins": prev_part.coins_earned if prev_part else 0,
        "summary": _season_summary(prev.state or {}, prev_part, names) if prev and prev_part else None,
        "core_count": me.core_count, "core_min": int(config.career_core_min),
        "carried_pct": me.carried_familiarity / 10, "keep_pct": int(config.career_core_keep_pct),
        "prev_formation": off.get("prev_formation"),
        "camp": me.camp, "camps": camp_options(config),
        "friendly": {"opponent": friendly["opponent"], "home_score": friendly["home_score"],
                     "away_score": friendly["away_score"]} if friendly else None,
        "starts_at": (state.get("schedule") or [None])[0],
    }


async def collection(db: AsyncSession, user: User) -> dict:
    """Own usable cards (and «Мой игрок») for building the season squad."""
    from app.schemas.card import UserCardOut

    config = await get_config(db)
    part = await _current_participation(db, user.id)
    cards = await _career_cards(db, user.id, config)
    squad = set(part.squad_card_ids or []) if part else set()
    out = []
    for card in cards:
        if not _usable(card):
            continue
        mine = getattr(card, "is_my_player", False)
        out.append({
            "card_id": card.id, "in_squad": card.id in squad,
            "card": UserCardOut.model_validate(card) if not mine else None,
            "my_player": {"name": card.player.display_name, "position": card.player.position.value,
                          "rating": card.player.rating, "club": card.player.club, "country": card.player.country}
            if mine else None,
        })
    return {"squad_size": int(config.career_squad_size), "cards": out}


async def friendly_events(db: AsyncSession, user: User, season_id: int) -> dict:
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    me = next(p for p in season.participants if p.user_id == user.id)
    friendly = _friendly_of(season.state or {}, me.team_index)
    if not friendly:
        raise NotFoundError("Товарищеский матч ещё не сыгран")
    return {
        "home_name": season.state["teams"][me.team_index]["name"], "away_name": friendly["opponent"],
        "home_score": friendly["home_score"], "away_score": friendly["away_score"], "events": friendly["events"],
        "analysis": friendly["analysis"], "my_side": "a",
    }


def _season_summary(state: dict, me: CareerParticipant, names: dict[int, str]) -> Optional[dict]:
    """Facts of a finished season for the coach, from the stored history
    only: points by tactic, the tactical interactions that applied for and
    against, top scorer, most minutes, most rounds missed."""
    results = state.get("results") or []
    if not results:
        return None
    team = me.team_index
    by_tactic: dict[str, dict] = {}
    duels: dict[tuple, dict] = {}
    goals: dict[int, int] = {}
    for round_results in results:
        for m in round_results:
            if team not in (m["home"], m["away"]):
                continue
            home = m["home"] == team
            own, opp = (m["hs"], m["as"]) if home else (m["as"], m["hs"])
            played = (m.get("tactics") or {}).get(str(team)) or {}
            key = played.get("preset") or "CUSTOM"
            row = by_tactic.setdefault(key, {"preset": key, "played": 0, "points": 0, "tactic": played.get("tactic")})
            row["played"] += 1
            row["points"] += 3 if own > opp else 1 if own == opp else 0
            analysis = (m.get("analysis") or {}).get(str(team)) or {}
            for d in analysis.get("duels") or []:
                agg = duels.setdefault((d["id"], d["attacker"]), {"id": d["id"], "label": d["label"], "attacker": d["attacker"],
                                                                  "applied": 0, "attacker_won": 0})
                agg["applied"] += d["applied"]
                agg["attacker_won"] += d["attacker_won"]
            side = "a" if home else "b"
            for e in m.get("events") or []:
                if e.get("event_type") == "goal" and e.get("team") == side:
                    sid = (e.get("payload") or {}).get("shooter_id")
                    if sid:
                        goals[sid] = goals.get(sid, 0) + 1
    minutes = {int(k): v for k, v in ((state.get("minutes") or {}).get(str(team)) or {}).items()}
    missed: dict[str, int] = {}
    for reports in (state.get("reports") or {}).values():
        report = reports.get(str(team)) or {}
        for name in (report.get("injured") or []) + (report.get("red") or []) + (report.get("suspended") or []):
            missed[name] = missed.get(name, 0) + 1
    top_scorer = max(goals.items(), key=lambda kv: kv[1]) if goals else None
    workhorse = max(minutes.items(), key=lambda kv: kv[1]) if minutes else None
    absent = max(missed.items(), key=lambda kv: kv[1]) if missed else None
    return {
        "tactics": sorted(by_tactic.values(), key=lambda r: (-r["points"], -r["played"])),
        "duels": sorted(duels.values(), key=lambda d: -d["applied"])[:6],
        "top_scorer": {"name": names.get(top_scorer[0], "Игрок"), "goals": top_scorer[1]} if top_scorer else None,
        "most_minutes": {"name": names.get(workhorse[0], "Игрок"), "minutes": workhorse[1]} if workhorse else None,
        "most_missed": {"name": absent[0], "rounds": absent[1]} if absent else None,
    }


async def _editable_participation(db: AsyncSession, user: User, round_index: Optional[int]) -> CareerParticipant:
    """The user's participation, locked for a lineup/tactics/plan change.
    Rounds whose time has come are played first (with the tactics saved
    until then) — the kick-off is the deadline — and the season row stays
    locked until the caller commits, so a round can't start mid-change.
    `round_index` = the round the client was preparing for: refused once
    that round has started."""
    part = await _current_participation(db, user.id)
    if part is None or part.status != "accepted":
        raise NotFoundError("Нет активного сезона")
    await resolve_due(db, part.season_id)
    season = await _lock_season(db, part.season_id)
    due = _round_at(season, season.rounds_played) if season.status == "active" else None
    if (round_index is not None and round_index != season.rounds_played) or (
        due is not None and due <= datetime.now(timezone.utc)
    ):
        raise ConflictError("Этот тур уже начался — тактика применится к следующему", details={"code": "round_started"})
    part = next(p for p in season.participants if p.user_id == user.id)
    await db.refresh(part)
    if part.status != "accepted":
        raise NotFoundError("Нет активного сезона")
    return part


async def set_lineup(
    db: AsyncSession, user: User, slots: dict[str, int], formation: str, mentality: str, playstyle: str,
    round_index: Optional[int] = None, tactic: Optional[dict] = None,
) -> None:
    """`tactic` (axes) for tactics seasons; without it a preset `playstyle`
    is taken as that preset's axes (older clients)."""
    part = await _editable_participation(db, user, round_index)
    if formation not in CLUB_FORMATIONS:
        raise ConflictError("Неизвестная схема")
    if mentality not in MENTALITIES:
        raise ConflictError("Неизвестная тактика")
    if tactic is not None:
        try:
            tactic = tactics.clean_tactic(tactic)
        except tactics.TacticError as exc:
            raise ConflictError(str(exc)) from exc
        playstyle = tactics.preset_of(tactic)
        season = await db.get(CareerSeason, part.season_id)
        if playstyle == tactics.CUSTOM and _tactics_version(season.state) < tactics.TACTICS_VERSION:
            raise ConflictError("В этом сезоне доступны только готовые стили — своя тактика появится в следующем")
    elif playstyle not in PLAYSTYLES:
        raise ConflictError("Неизвестная тактика")
    else:
        tactic = dict(tactics.PRESETS[playstyle])
    slot_defs = {s.code: s for s in get_formation_slots(formation)}
    cards = {c.id: c for c in await _career_cards(db, user.id)}
    squad_ids = _squad_ids(part, cards)
    used_players: set[str] = set()
    clean: dict[str, int] = {}
    for code, card_id in slots.items():
        slot, card = slot_defs.get(code), cards.get(card_id)
        if slot is None or card is None or card_id not in squad_ids:
            raise ConflictError("В составе можно использовать только карточки заявки")
        if card.player.position not in CATEGORY_POSITIONS[slot.category] or card_person(card) in used_players:
            raise ConflictError(f"{card.player.display_name} не подходит на позицию {code}")
        used_players.add(card_person(card))
        clean[code] = card_id
    part.formation, part.mentality, part.playstyle, part.tactic = formation, mentality, playstyle, tactic
    part.lineup = clean or None
    part.match_plan = tactics.drop_stale_subs(part.match_plan, set(slot_defs))
    await db.commit()


async def set_plan(
    db: AsyncSession, user: User, rules: list, subs: list, round_index: Optional[int] = None,
    set_pieces: Optional[dict] = None,
) -> None:
    """Saves the match plan (conditional instructions + substitutions, and
    set-piece takers/schemes when given) for the coming rounds; validated
    here, snapshotted at kick-off."""
    config = await get_config(db)
    part = await _editable_participation(db, user, round_index)
    season = await db.get(CareerSeason, part.season_id)
    if _tactics_version(season.state) < tactics.TACTICS_VERSION:
        raise ConflictError("План на матч доступен с нового сезона")
    cards = {c.id: c for c in await _career_cards(db, user.id, config)}
    slot_codes = {s.code for s in get_formation_slots(part.formation)}
    try:
        part.match_plan = tactics.clean_plan(
            {"rules": rules, "subs": subs}, slot_codes, set(_squad_ids(part, cards)), config,
        )
        if set_pieces is not None:
            part.set_pieces = tactics.clean_set_pieces(set_pieces, set(_squad_ids(part, cards)))
    except tactics.PlanError as exc:
        raise ConflictError(str(exc)) from exc
    await db.commit()


async def set_roles(db: AsyncSession, user: User, roles: Optional[dict], round_index: Optional[int] = None) -> None:
    """Player roles per line (winger / pivot / full-backs) for the coming rounds."""
    part = await _editable_participation(db, user, round_index)
    season = await db.get(CareerSeason, part.season_id)
    if _tactics_version(season.state) < tactics.TACTICS_VERSION:
        raise ConflictError("Роли игроков доступны с нового сезона")
    try:
        part.roles = tactics.clean_roles(roles) or None
    except tactics.TacticError as exc:
        raise ConflictError(str(exc)) from exc
    await db.commit()


async def set_marking(db: AsyncSession, user: User, marker_card_id: Optional[int], round_index: Optional[int] = None) -> None:
    """Man-marking of the next opponent's star (scouting) by one of my
    outfield players, for that round only; None clears it."""
    config = await get_config(db)
    part = await _editable_participation(db, user, round_index)
    season = await db.get(CareerSeason, part.season_id)
    if _tactics_version(season.state) < tactics.TACTICS_VERSION:
        raise ConflictError("Персональная опека доступна с нового сезона")
    if marker_card_id is None:
        part.marking = None
        await db.commit()
        return
    star = (_scouting(season, part, config) or {}).get("star")
    if not star:
        raise ConflictError("Звезда соперника неизвестна — опеку назначить нельзя")
    cards = {c.id: c for c in await _career_cards(db, user.id, config)}
    card = cards.get(marker_card_id)
    if card is None or marker_card_id not in _squad_ids(part, cards) or not _usable(card):
        raise ConflictError("Опекать может только игрок заявки")
    if card.player.position == Position.GK:
        raise ConflictError("Вратарь не может опекать игрока")
    part.marking = {"round": season.rounds_played, "marker": marker_card_id, "target": star["player_id"],
                    "target_name": star["name"]}
    await db.commit()


async def set_halftime(db: AsyncSession, user: User, orders: dict) -> None:
    """Half-time orders in the live match centre: until the second half
    starts, replaces any earlier orders for that match."""
    config = await get_config(db)
    part = await _current_participation(db, user.id)
    if part is None or part.status != "accepted":
        raise NotFoundError("Нет активного сезона")
    await resolve_due(db, part.season_id)
    season = await _lock_season(db, part.season_id)
    live = (season.state or {}).get("live") or {}
    me = next(p for p in season.participants if p.user_id == user.id)
    rec = next((m for m in (live.get("matches") or {}).values() if me.team_index in (m["home"], m["away"])), None)
    if not live or rec is None or datetime.fromisoformat(live["second_half_at"]) <= datetime.now(timezone.utc):
        raise ConflictError("Перерыв уже закончился", details={"code": "halftime_over"})
    side = rec["sides"][str(me.team_index)]
    try:
        clean = tactics.clean_halftime(
            orders, {x["card_id"] for x in side["on"]}, {x["card_id"] for x in side["bench"]},
            max(0, int(config.career_max_substitutions) - int(side.get("subs_used") or 0)),
        )
    except tactics.PlanError as exc:
        raise ConflictError(str(exc)) from exc
    state = copy.deepcopy(season.state)
    state["live"].setdefault("orders", {})[str(me.team_index)] = clean
    season.state = state
    flag_modified(season, "state")
    await db.commit()


def _live_out(season: CareerSeason, me: CareerParticipant, by_id: dict, config) -> Optional[dict]:
    """My match in the live match centre (first half played, break running)."""
    state = season.state or {}
    live = state.get("live") or {}
    match_index, rec = next(((int(k), m) for k, m in (live.get("matches") or {}).items()
                             if me.team_index in (m["home"], m["away"])), (None, None))
    if rec is None:
        return None
    teams = state.get("teams") or []
    side = rec["sides"].get(str(me.team_index)) or {}

    def player(entry: dict) -> dict:
        card = by_id.get(entry["card_id"])
        return {**entry, "name": card.player.display_name if card else "Игрок",
                "position": card.player.position.value if card else None,
                "rating": _effective(card) if card else None}

    return {
        "round": live["round"], "match_index": match_index, "second_half_at": live["second_half_at"],
        "home": rec["home"], "away": rec["away"],
        "home_name": teams[rec["home"]]["name"], "away_name": teams[rec["away"]]["name"],
        "hs": rec["hs"], "as": rec["as"], "events": rec["events"],
        "my_side": "a" if rec["home"] == me.team_index else "b",
        "on": [player(x) for x in side.get("on") or []], "bench": [player(x) for x in side.get("bench") or []],
        "subs_left": max(0, int(config.career_max_substitutions) - int(side.get("subs_used") or 0)),
        "mentality": side.get("mentality"), "tactic": side.get("tactic"),
        "orders": (live.get("orders") or {}).get(str(me.team_index)),
    }


def _plan_hints(part: CareerParticipant, xi: list, config, scouting: Optional[dict]) -> list[dict]:
    """What the coach could still add to the plan for the next match."""
    plan = part.match_plan or {}
    subs, rules = plan.get("subs") or [], plan.get("rules") or []
    fresh = tactics.tuning_of(config)["sub_fresh"]
    hints = []
    tired = [card.player.display_name for card, _ in xi if _condition(part, card.id)["fatigue"] >= 70]
    if tired and len(subs) < len(tired):
        hints.append({"code": "tired", "text": f"Усталость 70+: {', '.join(tired[:4])}"
                      f"{' и др.' if len(tired) > 4 else ''}. Добавь замены: свежий игрок получает +{fresh} к рейтингу."})
    elif not subs:
        hints.append({"code": "no_subs", "text": f"В плане нет замен. К концу матча основа устаёт, "
                      f"а вышедший со скамейки получает +{fresh} к рейтингу."})
    if not any(r.get("score") == "behind" for r in rules):
        hints.append({"code": "no_behind_rule", "text": "Нет указания на случай, если проигрываем — "
                      "например, атакующий настрой с 60-й минуты."})
    star = (scouting or {}).get("star")
    if star and not ((part.marking or {}).get("round") == (scouting or {}).get("round_index")):
        hints.append({"code": "star", "text": f"У соперника звезда — {star['name']} ({star['rating']}). "
                      "Можно назначить персональную опеку."})
    tactic, roles = _my_tactic(part), part.roles or {}
    has_wingers = any(s.ideal_position.value in tactics.ROLE_GROUPS["winger"]["positions"]
                      for s in get_formation_slots(part.formation))
    if has_wingers and "winger" not in roles and tactic.get("direction") in ("wings", "center"):
        role = "crosser" if tactic["direction"] == "wings" else "inside"
        hints.append({"code": "roles", "text": f"Атака через {'фланги' if role == 'crosser' else 'центр'}: "
                      f"дай крайним роль «{tactics.ROLE_LABELS['winger'][role]}»."})
    return hints


# --- playing rounds ------------------------------------------------------------

def standings(state: dict) -> list[dict]:
    table = {t["index"]: {"team_index": t["index"], "played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0}
             for t in state.get("teams", [])}
    for round_results in state.get("results", []):
        for m in round_results:
            for me, them, gf, ga in ((m["home"], m["away"], m["hs"], m["as"]), (m["away"], m["home"], m["as"], m["hs"])):
                row = table[me]
                row["played"] += 1
                row["gf"] += gf
                row["ga"] += ga
                if gf > ga:
                    row["won"] += 1
                    row["points"] += 3
                elif gf == ga:
                    row["drawn"] += 1
                    row["points"] += 1
                else:
                    row["lost"] += 1
    return sorted(table.values(), key=lambda r: (-r["points"], -(r["gf"] - r["ga"]), -r["gf"], r["team_index"]))


async def _credit(db: AsyncSession, user_id: int, amount: int, description: str, season_id: int) -> int:
    if amount <= 0:
        return 0
    locked = await wallet_service.lock_user_for_update(db, user_id)
    await wallet_service.credit_coins(
        db, locked, amount, TransactionType.career_reward, description,
        related_object_type="career_season", related_object_id=season_id,
    )
    return amount


CATEGORY_LABELS_RU = {"GK": "вратарей", "DEF": "защитников", "MID": "полузащитников", "FWD": "нападающих"}


def _squad_warnings(part: CareerParticipant, by_id: dict, next_round: int, xi: list) -> list[dict]:
    """Holes and thin lines for the next round: "critical" = the XI has a
    player out of his line (nobody fit to cover it), "thin" = exactly as
    many fit players as the formation needs — one injury or ban away from
    playing someone out of position."""
    slots = get_formation_slots(part.formation)
    need: dict[str, int] = {}
    for s in slots:
        need[s.category] = need.get(s.category, 0) + 1
    fit: dict[str, int] = {cat: 0 for cat in need}
    for cid in _squad_ids(part, by_id):
        card = by_id.get(cid)
        if card is None or not _usable(card) or _is_out(part, cid, next_round):
            continue
        for cat, positions in CATEGORY_POSITIONS.items():
            if card.player.position in positions and cat in fit:
                fit[cat] += 1
    out = []
    for card, slot in xi:
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            out.append({"level": "critical", "category": slot.category,
                        "text": f"На позиции {slot.code} сыграет {card.player.display_name} не по амплуа — "
                                f"в заявке нет свободных {CATEGORY_LABELS_RU[slot.category]}"})
    for cat, n in need.items():
        if fit[cat] == n and not any(w["category"] == cat for w in out):
            out.append({"level": "thin", "category": cat,
                        "text": f"Здоровых {CATEGORY_LABELS_RU[cat]} ровно {n} — травма или дисквалификация "
                                f"оставит дыру. Добавь запасного в заявку."})
    return out


def _my_tactic(part: CareerParticipant) -> dict:
    return tactics.tactic_for(part.tactic, part.playstyle)


# --- cup -------------------------------------------------------------------------------------

# The cup round played right after these league rounds (0-based): the
# evenings of days 2, 3, 5 and 7 — a double match day, rotation matters.
CUP_AFTER_ROUNDS = (3, 5, 9, 13)
CUP_ROUND_NAMES = ("1/8 финала", "1/4 финала", "1/2 финала", "Финал")
CUP_CLUB_NAMES = [
    "Химик", "Энергия", "Локомотив Степной", "Факел", "Авангард", "Ротор Приречье", "Шахтёр Горный", "Волна",
    "Кристалл", "Олимп", "Сатурн", "Нефтяник", "Луч", "Арсенал Озёрный", "Звезда Севера", "Прибой",
]


def _cup_team(state: dict, index: int) -> dict:
    if index < len(state.get("teams") or []):
        return state["teams"][index]
    return next(t for t in state["cup"]["extra"] if t["index"] == index)


async def _create_cup(db: AsyncSession, season: CareerSeason, state: dict, human_avg: float, config) -> None:
    """16 teams: the league plus 8 bots from the neighbouring divisions
    (four stronger, four weaker); a seeded open draw."""
    extra = await _build_bots(
        db, season, list(range(TEAMS, TEAMS * 2)), human_avg, config,
        name_pool=CUP_CLUB_NAMES, seed_salt=1, spreads=[-7, -6, -5, -4, 4, 5, 6, 7],
    )
    rng = random.Random(season.id * 3571)
    entrants = list(range(TEAMS * 2))
    rng.shuffle(entrants)
    ties = [[entrants[i], entrants[i + 1]] for i in range(0, len(entrants), 2)]
    state["cup"] = {
        "extra": extra,
        "rounds": [{"after_round": r, "ties": ties if k == 0 else [], "results": []} for k, r in enumerate(CUP_AFTER_ROUNDS)],
        "rotation": {}, "winner": None,
    }


async def set_cup_rotation(db: AsyncSession, user: User, rotation: bool) -> None:
    """Cup matches with the freshest players instead of the league XI."""
    part = await _editable_participation(db, user, None)
    season = await _lock_season(db, part.season_id)
    if not (season.state or {}).get("cup"):
        raise ConflictError("В этом сезоне нет кубка")
    state = copy.deepcopy(season.state)
    state["cup"].setdefault("rotation", {})[str(part.team_index)] = bool(rotation)
    season.state = state
    flag_modified(season, "state")
    await db.commit()


def _cup_out(state: dict, me: CareerParticipant, config) -> Optional[dict]:
    cup = state.get("cup")
    if not cup:
        return None
    schedule = state.get("schedule") or []
    rounds = []
    alive = True
    for k, rnd in enumerate(cup["rounds"]):
        ties = []
        for i, (a, b) in enumerate(rnd["ties"]):
            res = rnd["results"][i] if i < len(rnd["results"]) else None
            mine = me.team_index in (a, b)
            if res and mine and res["winner"] != me.team_index:
                alive = False
            ties.append({
                "a": a, "b": b, "a_name": _cup_team(state, a)["name"], "b_name": _cup_team(state, b)["name"],
                "sa": res["sa"] if res else None, "sb": res["sb"] if res else None,
                "pens": res.get("pens") if res else None, "winner": res["winner"] if res else None,
                "has_events": bool(res and res.get("events")), "mine": mine,
            })
        rounds.append({
            "name": CUP_ROUND_NAMES[k], "after_round": rnd["after_round"],
            "at": schedule[rnd["after_round"]] if rnd["after_round"] < len(schedule) else None, "ties": ties,
        })
    rewards = list(config.career_cup_rewards or [0, 0, 0])
    return {
        "rounds": rounds, "winner": cup.get("winner"),
        "status": "winner" if cup.get("winner") == me.team_index else ("alive" if alive else "out"),
        "rotation": bool((cup.get("rotation") or {}).get(str(me.team_index), False)),
        "rewards": {"winner": rewards[0] if rewards else 0, "final": rewards[1] if len(rewards) > 1 else 0,
                    "semi": rewards[2] if len(rewards) > 2 else 0},
        "rep_winner": int(config.career_rep_cup),
    }


def _tactics_version(state: dict) -> int:
    return int((state or {}).get("tactics_version") or 0)


def _bot_roles(tactic: dict) -> dict:
    """Roles a bot coach picks to fit its own tactic."""
    roles = {}
    if tactic.get("direction") == "wings":
        roles["winger"], roles["fullback"] = "crosser", "attacking"
    elif tactic.get("direction") == "center":
        roles["winger"] = "inside"
    if tactic.get("block") == "low":
        roles["pivot"] = "destroyer"
        if tactic.get("direction") != "wings":
            roles["fullback"] = "holding"
    elif tactic.get("buildup") == "short":
        roles["pivot"] = "playmaker"
    return roles


def _bot_runner(team: dict, label: str, round_index: int, config, chem_rules, choice: dict):
    on_pitch = [tactics.LivePlayer(card=c, base_rating=c.player.rating, pre_fatigue=0, slot=slot)
                for c, slot in _bot_cards(team, round_index, config)]
    return tactics.CareerSideRunner(
        label, team["name"], team["formation"], team["mentality"], choice["tactic"], on_pitch, [], config,
        familiarity=choice["familiarity"], plan=choice["plan"], chem_rules=chem_rules,
        set_pieces=team.get("set_pieces"), roles=_bot_roles(choice["tactic"]),
    )


def _star(players: list) -> Optional[tactics.LivePlayer]:
    """The best outfield player of a side (the one worth man-marking)."""
    outfield = [p for p in players if p.slot is not None and p.slot.category != "GK"]
    return max(outfield, key=lambda p: (p.base_rating, -p.card.id)) if outfield else None


def _bot_marking(bot: tactics.CareerSideRunner, human: tactics.CareerSideRunner) -> Optional[dict]:
    """A «Легенда» bot man-marks the human's best player with its best
    defensive midfielder or centre-back."""
    star = _star(human.on_pitch)
    markers = [p for p in bot.on_pitch if p.slot.ideal_position.value in ("CDM", "CB")]
    if star is None or not markers:
        return None
    marker = max(markers, key=lambda p: (p.base_rating, -p.card.id))
    return {"marker": marker.card.id, "target": star.card.player_id}


def _match_seed(season_id: int, round_index: int, match_index: int) -> int:
    return season_id * 1_000_003 + round_index * 1_009 + match_index * 31 + 7


@contextlib.contextmanager
def _seeded(seed: int):
    """Runs a career match on a fixed seed (the live match centre replays
    the first half exactly when the second half is played) without making
    the process-wide RNG predictable for anything else."""
    saved = random.getstate()
    random.seed(seed)
    try:
        yield
    finally:
        random.setstate(saved)


def _human_runner(
    part: CareerParticipant, cards: list, config, chem_rules, label: str, team_name: str, *,
    avail_round: int, rotate: bool = False, training: Optional[str] = None, profile=None,
    marking: Optional[dict] = None,
    base_fx: Optional[dict] = None,
):
    """The human side for a match: XI (holes filled out of position), bench,
    pre-match fatigue / form, club tenure, familiarity and the plan.
    Returns (runner, pairs, base_familiarity) — runner None when fewer than
    eleven fit players exist in the whole collection."""
    by_id = {c.id: c for c in cards}
    pairs = resolve_lineup(part, by_id, avail_round, [c for c in cards if _usable(c)], fill_any_position=True,
                           rotate=rotate)
    if len(pairs) != len(get_formation_slots(part.formation)):
        return None, [], 0
    xi_ids = {c.id for c, _ in pairs}
    xi_players = {card_person(c) for c, _ in pairs}
    bench = [by_id[cid] for cid in _squad_ids(part, by_id) if cid in by_id]
    bench = [c for c in bench if _usable(c) and not _is_out(part, c.id, avail_round)
             and c.id not in xi_ids and card_person(c) not in xi_players]
    tr = tactics.tuning_of(config)["training"]

    def live(card, slot=None):
        engine_card = _engine_card(card, config)
        cond = _condition(part, card.id)
        base = min(99, engine_card.player.rating + league_service.tenure_bonus(profile, card.id, config))
        return tactics.LivePlayer(card=engine_card, base_rating=base, pre_fatigue=cond["fatigue"], form=cond["form"],
                                  slot=slot)

    base_familiarity = tactics.familiarity_for(
        part.familiarity, part.familiar_formation, part.familiar_tactic, part.formation, _my_tactic(part), config,
    )
    familiarity = base_familiarity
    if training == "tactical":  # this match only; growth counts from the base
        familiarity = min(int(config.career_familiarity_max_tenths) + tr["tactical_familiarity_tenths"],
                          familiarity + tr["tactical_familiarity_tenths"])
    runner = tactics.CareerSideRunner(
        label, team_name, part.formation, part.mentality, _my_tactic(part),
        [live(c, slot) for c, slot in pairs], [live(c) for c in bench], config,
        familiarity=familiarity, plan=copy.deepcopy(part.match_plan), chem_rules=chem_rules,
        set_pieces=part.set_pieces, training=training, roles=part.roles, marking=marking,
        # «Клубная база» analytics centre makes these two trainings stronger.
        boost=club_base_service.prep_boost(tr["opponent_boost"], base_fx or {}) if training == "opponent" else 1.0,
        set_piece_boost=club_base_service.prep_boost(tr["set_piece_boost"], base_fx or {})
        if training == "set_pieces" else 1.0,
    )
    return runner, pairs, base_familiarity



async def _apply_club_artifacts(db: AsyncSession, teams: list, home: int, away: int, run_h, run_a, config) -> None:
    """«Артефакты» of the human sides (artifact_service): team_boost_pct
    makes their own side stronger, opp_home_pct weakens the visitors when
    they play at home (both act on the runners' `boost`), and card bonuses
    raise the base rating of the owner's cards of a given player (that
    part comes in through card_rating_bonus, see refresh_card_bonuses)."""
    from app.services import artifact_service

    for index, runner, other, at_home in ((home, run_h, run_a, True), (away, run_a, run_h, False)):
        user_id = teams[index].get("user_id")
        if not user_id:
            continue
        effects = await artifact_service.effects_of(db, user_id, "club", config)
        # Card bonuses (e.g. Maradona's shirt: +3 to the owner's Maradona
        # cards) are on the card rows now and already in base_rating via
        # card_rating_bonus — adding them here again would double them.
        if effects.get("team_boost_pct"):
            runner.boost *= 1 + effects["team_boost_pct"] / 100
        if at_home and effects.get("opp_home_pct"):
            other.boost *= 1 - effects["opp_home_pct"] / 100

async def _play_round(db: AsyncSession, season: CareerSeason, round_index: int, config, live: bool = False) -> None:
    """Plays a round. live=True (live match centre) only plays the first
    half of the matches with a human, stores it in state["live"] and
    changes nothing else; the real pass later replays them on the same
    seeds with the half-time orders applied."""
    state = copy.deepcopy(season.state)
    teams = state["teams"]
    humans = {p.team_index: p for p in season.participants if p.status in ("accepted", "left")}
    cards_cache: dict[int, list[UserCard]] = {}
    played: dict[int, set[int]] = {}
    v1 = _tactics_version(state) >= tactics.TACTICS_VERSION
    # tactics_version >= 1: every team's played tactic per round (scouting,
    # adaptive bots — they only ever read rounds already played), minutes
    # per card (post-match fatigue) and the familiarity each human used.
    history: dict = state.setdefault("played_tactics", {}) if v1 else {}
    chem_rules = chemistry_service.rules_from_dict(state.get("chemistry_rules")) if v1 else None
    bot_states: dict = state.setdefault("bot_tactics", {}) if v1 else {}
    minutes_by_team: dict[int, dict[int, int]] = {}
    gains_by_team: dict[int, dict[int, int]] = {}
    cup_played: dict[int, set[int]] = {}
    profiles: dict[int, CareerProfile] = {}
    if v1:
        for ti, p in humans.items():
            if p.status == "accepted":
                profiles[ti] = await get_profile(db, p.user_id, config)
    used_familiarity: dict[int, int] = {}
    # «Клубная база»: effects frozen on the participant for the season.
    base_fx: dict[int, dict] = {}
    for ti, p in humans.items():
        if p.status == "accepted":
            base_fx[ti] = await club_base_service.career_effects(db, p, config)

    async def human_cards(part: CareerParticipant) -> list:
        if part.user_id not in cards_cache:
            cards_cache[part.user_id] = await _career_cards(db, part.user_id, config)
        return cards_cache[part.user_id]

    async def side_for(team_index: int):
        team = teams[team_index]
        if team.get("user_id") is None:
            return _bot_side(team, round_index, config)
        part = humans.get(team_index)
        if part is None or part.status != "accepted":
            return None  # left the season / declined: technical defeat
        cards = await human_cards(part)
        pairs = resolve_lineup(part, {c.id: c for c in cards}, round_index, [c for c in cards if _usable(c)])
        played[team_index] = {c.id for c, _ in pairs}
        return _human_side(part, pairs, config)

    live_state = (season.state or {}).get("live") or {}
    orders = (live_state.get("orders") or {}) if live_state.get("round") == round_index else {}
    saved_conditions = {p.id: copy.deepcopy(p.condition) for p in humans.values()} if live else {}

    async def runner_for(team_index: int, label: str, opponent_index: int, cup: bool = False):
        team = _cup_team(state, team_index)
        if team.get("user_id") is None:
            opponent_human = _cup_team(state, opponent_index).get("user_id") is not None
            roll = random.Random(season.id * 7919 + round_index * 131 + team_index).random()
            seen = history.get(str(opponent_index), []) if opponent_human else []
            if opponent_human and not seen:
                # Nothing played this season yet: a club remembers the
                # tactic that beat it twice before (living league).
                remembered = league_service.remembered_tactic(profiles.get(opponent_index), team.get("club_id"))
                if remembered in tactics.PRESETS:
                    seen = [{"tactic": tactics.PRESETS[remembered], "preset": remembered}]
            choice = tactics.bot_tactics_for_round(
                team, season.difficulty, seen, bot_states.get(str(team_index), {}), config, roll,
            )
            if not cup:
                bot_states[str(team_index)] = {
                    "tactic": choice["tactic"], "adapted": choice["adapted"],
                    "familiarity": tactics.familiarity_after_match(choice["familiarity"], config)
                    if season.difficulty == "legend" else 0,
                }
            return _bot_runner(team, label, round_index, config, chem_rules, choice)
        part = humans.get(team_index)
        if part is None or part.status != "accepted":
            return None  # left the season / declined: technical defeat
        cards = await human_cards(part)
        by_id = {c.id: c for c in cards}
        training = part.training if part.training in TRAININGS and not cup else None
        tr = tactics.tuning_of(config)["training"]
        if training:
            # Training load / recovery before kick-off, kept in the condition.
            delta = tr["recovery_fatigue"] if training == "recovery" else tr["load_fatigue"]
            if training == "recovery":  # «Клубная база» medical centre
                delta -= int(base_fx.get(team_index, {}).get("recovery", 0))
            condition = dict(part.condition or {})
            for cid in _squad_ids(part, by_id):
                entry = {**_FRESH, **condition.get(str(cid), {})}
                entry["fatigue"] = max(0, min(100, entry["fatigue"] + delta))
                condition[str(cid)] = entry
            part.condition = condition
            flag_modified(part, "condition")
        # A cup tie follows the league match the same evening: players hurt
        # or banned there are already out; with rotation the freshest play.
        runner, pairs, base_familiarity = _human_runner(
            part, cards, config, chem_rules, label, team["name"],
            avail_round=round_index + 1 if cup else round_index,
            rotate=cup and bool(((state.get("cup") or {}).get("rotation") or {}).get(str(team_index))),
            training=training, profile=profiles.get(team_index),
            marking=part.marking if not cup and (part.marking or {}).get("round") == round_index else None,
            base_fx=base_fx.get(team_index),
        )
        if runner is None:
            return None  # fewer than 11 fit players in the whole collection
        if not cup:
            runner.halftime = orders.get(str(team_index))
        (cup_played if cup else played)[team_index] = {c.id for c, _ in pairs}
        if not cup:
            used_familiarity[team_index] = base_familiarity
        return runner

    results = []
    live_matches: dict = {}
    for match_index, (home, away) in enumerate(state["fixtures"][round_index]):
        with_human = bool(teams[home].get("user_id") or teams[away].get("user_id"))
        if live and not with_human:
            continue
        events = None
        extra: dict = {}
        if v1:
            run_h, run_a = await runner_for(home, "a", away), await runner_for(away, "b", home)
            if run_h and run_a:
                await _apply_club_artifacts(db, teams, home, away, run_h, run_a, config)
                await path_match_service.career_apply_talents(
                    db, (run_h, run_a), {c.id: c for cards in cards_cache.values() for c in cards}, config,
                )
                if season.difficulty == "legend":
                    for bot, human, bot_index in ((run_h, run_a, home), (run_a, run_h, away)):
                        if teams[bot_index].get("user_id") is None and teams[away if bot is run_h else home].get("user_id"):
                            bot.marking = _bot_marking(bot, human)
                tracker: dict = {}
                # Starting XIs for the 2D replay (career_replay_service);
                # taken before kick-off, substitutions come from the events.
                lineups = {"a": career_replay.lineup_record(run_h), "b": career_replay.lineup_record(run_a)}
                with _seeded(_match_seed(season.id, round_index, match_index)):
                    match = tournament_match_engine.simulate_match_controlled(
                        tactics.CareerMatchController(run_h, run_a), config, teams[home]["name"], teams[away]["name"],
                        tracker=tracker,
                    )
                if live:
                    live_matches[str(match_index)] = {**_live_record(match, run_h, run_a, home, away), "lineups": lineups}
                    continue
                hs, as_ = match.score_a, match.score_b
                extra["tactics"] = {}
                for index, runner in ((home, run_h), (away, run_a)):
                    played_tactic = {"formation": runner.formation, "mentality": runner.mentality,
                                     "tactic": runner.tactic, "preset": tactics.preset_of(runner.tactic)}
                    extra["tactics"][str(index)] = played_tactic
                    history.setdefault(str(index), []).append({"round": round_index, **played_tactic})
                    minutes_by_team[index] = runner.minutes_played()
                    gains_by_team[index] = runner.fatigue_gained()
                    if index in played:
                        played[index] = {cid for cid, mins in minutes_by_team[index].items() if mins > 0}
                if with_human:
                    events = match.event_log
                    extra["lineups"] = lineups
                    extra["analysis"] = {
                        str(index): tactics.build_analysis(match.event_log, tracker, label, runner, other)
                        for index, label, runner, other in ((home, "a", run_h, run_a), (away, "b", run_a, run_h))
                        if teams[index].get("user_id")
                    }
            elif not run_h and not run_a:
                hs, as_ = 0, 0
            else:
                hs, as_ = (0, 3) if not run_h else (3, 0)
        else:
            side_h, side_a = await side_for(home), await side_for(away)
            if side_h and side_a:
                match = tournament_match_engine.simulate_match(
                    side_h[0], side_a[0], side_h[1], side_a[1], config, teams[home]["name"], teams[away]["name"],
                )
                hs, as_ = match.score_a, match.score_b
                if with_human:
                    events = match.event_log
            elif not side_h and not side_a:
                hs, as_ = 0, 0
            else:
                hs, as_ = (0, 3) if not side_h else (3, 0)
        results.append({"home": home, "away": away, "hs": hs, "as": as_, "events": events, **extra})
    if live:
        for part in humans.values():
            part.condition = saved_conditions.get(part.id, part.condition)
        if not live_matches:
            return
        at = _round_at(season, round_index)
        second_half = at + timedelta(minutes=int(config.career_halftime_minutes))
        fresh = copy.deepcopy(season.state)
        fresh["live"] = {"round": round_index, "second_half_at": second_half.isoformat(), "matches": live_matches,
                         "orders": {}}
        season.state = fresh
        flag_modified(season, "state")
        for team_index, part in humans.items():
            if part.status != "accepted":
                continue
            rec = next((m for m in live_matches.values() if team_index in (m["home"], m["away"])), None)
            if rec is None:
                continue
            own, opp = (rec["hs"], rec["as"]) if rec["home"] == team_index else (rec["as"], rec["hs"])
            await notify(
                db, part.user_id, NotificationType.career_round_result, f"Карьера, тур {round_index + 1}: перерыв {own}:{opp}",
                f"Первый тайм окончен. {int(config.career_halftime_minutes)} мин на указания: замены, настрой, тактика.",
                related_object_type="career_season", related_object_id=season.id,
            )
        return
    state.pop("live", None)
    state["results"].append(results)

    rng = random.Random(season.id * 104729 + round_index)
    reports = state.setdefault("reports", {}).setdefault(str(round_index), {})
    for team_index, part in humans.items():
        if part.status != "accepted":
            continue
        match = next(m for m in results if team_index in (m["home"], m["away"]))
        is_home = match["home"] == team_index
        own, opp = (match["hs"], match["as"]) if is_home else (match["as"], match["hs"])
        opponent = teams[match["away"] if is_home else match["home"]]["name"]
        own_cards = {c.id: c for c in cards_cache.get(part.user_id, [])}
        names = {cid: c.player.display_name for cid, c in own_cards.items()}
        gains = gains_by_team.get(team_index)
        if gains is not None and part.camp == "physical" and round_index < int(config.career_camp_physical_rounds):
            keep = 100 - int(config.career_camp_physical_pct)
            gains = {cid: g * keep // 100 for cid, g in gains.items()}
        if team_index in profiles:
            opp_team = teams[match["away"] if is_home else match["home"]]
            my_preset = ((match.get("tactics") or {}).get(str(team_index)) or {}).get("preset")
            league_service.record_meeting(profiles[team_index], opp_team.get("club_id"), own, opp, my_preset)
            league_service.add_tenure(profiles[team_index], minutes_by_team.get(team_index, {}))
            season_minutes = state.setdefault("minutes", {}).setdefault(str(team_index), {})
            for cid, mins in minutes_by_team.get(team_index, {}).items():
                season_minutes[str(cid)] = season_minutes.get(str(cid), 0) + mins
        unlocked_text = ""
        if v1 and team_index in profiles:
            hint = (((match.get("analysis") or {}).get(str(team_index)) or {}).get("matchup") or {}).get("hint")
            new = achievements.record_match(profiles[team_index], own, opp, events=match.get("events"),
                                            side="a" if is_home else "b", matchup_hint=hint)
            unlocked_text = await _grant_achievements(db, part, new, config, season.id)
        gains = await path_match_service.career_fatigue_gains(db, gains, own_cards, config)
        report = _after_match(
            part, played.get(team_index, set()), own, opp, round_index, config, rng, names, _squad_ids(part, own_cards),
            gains=gains, base_fx=base_fx.get(team_index),
            card_mult=tactics.tuning_of(config)["foul"][_my_tactic(part).get("tackling", "normal")] if v1 else 1.0,
        )
        reports[str(team_index)] = report
        flag_modified(part, "condition")
        if team_index in used_familiarity and team_index in minutes_by_team:
            part.familiarity = tactics.familiarity_after_match(
                used_familiarity[team_index], config,
                bonus_pct=int(base_fx.get(team_index, {}).get("familiarity_pct", 0)),
            )
            part.familiar_formation, part.familiar_tactic = part.formation, _my_tactic(part)

        reward = config.career_match_reward_win if own > opp else config.career_match_reward_draw if own == opp else 0
        part.coins_earned += await _credit(db, part.user_id, reward, f"Карьера: тур {round_index + 1}", season.id)
        # «Клубная база»: the stadium (+ hotel, ticket prices) earns on home matches.
        matchday = club_base_service.matchday_income(base_fx.get(team_index, {})) if is_home else 0
        if matchday > 0:
            locked = await wallet_service.lock_user_for_update(db, part.user_id)
            await wallet_service.credit_coins(
                db, locked, matchday, TransactionType.club_base_matchday, f"Стадион: домашний матч, тур {round_index + 1}",
                related_object_type="career_season", related_object_id=season.id,
            )
            part.coins_earned += matchday
        # «Академия»: experience for the path cards that played this league
        # round (own daily cap per card; idempotent per card and round).
        await path_match_service.award_side(
            db, user_id=part.user_id, source_type="career", source_id=f"{season.id}:{round_index}",
            card_ids=played.get(team_index, set()), own=own, opp=opp, event_log=match.get("events") or [],
            side="a" if is_home else "b", config=config,
        )
        if my_player_service.card_id_for(part.user_id) in played.get(team_index, set()):
            locked = await wallet_service.lock_user_for_update(db, part.user_id)
            my_player_service.add_xp(
                locked, config.my_player_xp_career_match, config,
                bonus_pct=await my_player_service.xp_bonus_pct(db, part.user_id),
            )
        outcome = "Победа" if own > opp else "Ничья" if own == opp else "Поражение"
        await notify(
            db, part.user_id, NotificationType.career_round_result, f"Карьера, тур {round_index + 1}: {outcome}",
            f"{own}:{opp} против «{opponent}»" + (f" · +{reward} монет" if reward else "")
            + (f" · стадион +{matchday}" if matchday else "") + _report_line(report)
            + unlocked_text,
            related_object_type="career_season", related_object_id=season.id,
        )

    if v1 and state.get("cup") and round_index in CUP_AFTER_ROUNDS:
        await _play_cup_round(
            db, season, state, round_index, config, humans, runner_for, cup_played, cards_cache, rng,
        )

    season.state = state
    flag_modified(season, "state")
    season.rounds_played = round_index + 1
    if season.rounds_played >= ROUNDS:
        await _finish(db, season, config)


async def _play_cup_round(db, season, state, round_index, config, humans, runner_for, cup_played, cards_cache, rng) -> None:
    cup = state["cup"]
    k = CUP_AFTER_ROUNDS.index(round_index)
    rnd = cup["rounds"][k]
    results = []
    for a, b in rnd["ties"]:
        team_a, team_b = _cup_team(state, a), _cup_team(state, b)
        with_human = bool(team_a.get("user_id") or team_b.get("user_id"))
        run_a, run_b = await runner_for(a, "a", b, cup=True), await runner_for(b, "b", a, cup=True)
        if run_a and run_b:
            await path_match_service.career_apply_talents(
                db, (run_a, run_b), {c.id: c for cards in cards_cache.values() for c in cards}, config,
            )
        res: dict = {"a": a, "b": b, "events": None, "pens": None}
        if run_a and run_b:
            tracker: dict = {}
            lineups = {"a": career_replay.lineup_record(run_a), "b": career_replay.lineup_record(run_b)}
            match = tournament_match_engine.simulate_match_controlled(
                tactics.CareerMatchController(run_a, run_b), config, team_a["name"], team_b["name"], tracker=tracker,
            )
            res.update(sa=match.score_a, sb=match.score_b)
            if match.score_a == match.score_b:
                pa, pb, kicks = tactics.penalty_shootout(run_a, run_b)
                res["pens"] = [pa, pb]
                res["kicks"] = kicks
                winner = a if pa > pb else b
            else:
                winner = a if match.score_a > match.score_b else b
            if with_human:
                res["events"] = match.event_log
                res["lineups"] = lineups
                res["analysis"] = {
                    str(index): tactics.build_analysis(match.event_log, tracker, label, runner, other)
                    for index, label, runner, other in ((a, "a", run_a, run_b), (b, "b", run_b, run_a))
                    if _cup_team(state, index).get("user_id")
                }
            for index, runner in ((a, run_a), (b, run_b)):
                part = humans.get(index)
                if part is None or part.status != "accepted":
                    continue
                own_cards = {c.id: c for c in cards_cache.get(part.user_id, [])}
                own, opp = (res["sa"], res["sb"]) if index == a else (res["sb"], res["sa"])
                report = _after_match(
                    part, {cid for cid, m in runner.minutes_played().items() if m > 0}, own, opp, round_index, config,
                    rng, {cid: c.player.display_name for cid, c in own_cards.items()}, _squad_ids(part, own_cards),
                    gains=runner.fatigue_gained(),
                    card_mult=tactics.tuning_of(config)["foul"][_my_tactic(part).get("tackling", "normal")],
                    base_fx=part.base_effects,
                )
                state.setdefault("cup_reports", {}).setdefault(str(k), {})[str(index)] = report
                flag_modified(part, "condition")
        else:
            res.update(sa=3 if run_a else 0, sb=3 if run_b else 0)
            winner = a if run_a else b
        res["winner"] = winner
        results.append(res)
    rnd["results"] = results

    winners = [r["winner"] for r in results]
    if k + 1 < len(cup["rounds"]):
        cup["rounds"][k + 1]["ties"] = [[winners[i], winners[i + 1]] for i in range(0, len(winners), 2)]
    else:
        cup["winner"] = winners[0]

    rewards = list(config.career_cup_rewards or [0, 0, 0])
    stage_reward = {2: rewards[2] if len(rewards) > 2 else 0, 3: rewards[1] if len(rewards) > 1 else 0}
    for res in results:
        for index in (res["a"], res["b"]):
            part = humans.get(index)
            if part is None or part.status != "accepted":
                continue
            won = res["winner"] == index
            own, opp = (res["sa"], res["sb"]) if index == res["a"] else (res["sb"], res["sa"])
            opponent = _cup_team(state, res["b"] if index == res["a"] else res["a"])["name"]
            score = f"{own}:{opp}" + (f" (пен. {res['pens'][0] if index == res['a'] else res['pens'][1]}:"
                                      f"{res['pens'][1] if index == res['a'] else res['pens'][0]})" if res.get("pens") else "")
            coins, text = 0, ""
            if k == len(cup["rounds"]) - 1 and won:
                coins = await _credit(db, part.user_id, rewards[0] if rewards else 0, "Карьера: победа в кубке", season.id)
                profile = await get_profile(db, part.user_id, config)
                profile.reputation += club_base_service.reputation_gain(int(config.career_rep_cup), part.base_effects or {})
                text = "Кубок твой!"
            elif not won and k in stage_reward:
                coins = await _credit(db, part.user_id, stage_reward[k], f"Карьера: {CUP_ROUND_NAMES[k]} кубка", season.id)
                text = "Вылет из кубка"
            else:
                text = "Проход дальше" if won else "Вылет из кубка"
            part.coins_earned += coins
            await notify(
                db, part.user_id, NotificationType.career_round_result, f"Кубок, {CUP_ROUND_NAMES[k]}: {text}",
                f"{score} против «{opponent}»" + (f" · +{coins} монет" if coins else ""),
                related_object_type="career_season", related_object_id=season.id,
            )


def _after_match(
    part: CareerParticipant, played_ids: set[int], own: int, opp: int, round_index: int, config,
    rng: random.Random, names: dict[int, str], squad_ids: Optional[list[int]] = None,
    gains: Optional[dict[int, int]] = None, card_mult: float = 1.0, base_fx: Optional[dict] = None,
) -> dict:
    """Fatigue, injuries, yellow/red cards and form for one human squad after
    a round. Returns the round report (player names per event) shown in the
    calendar and the result notification. `gains` (tactics seasons: card id
    -> fatigue built up in the match, by minutes played and the tactic's
    pressing load) replaces the flat career_fatigue_per_match."""
    report: dict[str, list[str]] = {"yellow": [], "red": [], "suspended": [], "injured": [], "form_up": [], "form_down": []}
    condition = dict(part.condition or {})
    for card_id in (squad_ids if squad_ids is not None else part.squad_card_ids):
        entry = {**_FRESH, **condition.get(str(card_id), {})}
        name = names.get(card_id, "Игрок")
        if card_id in played_ids:
            tired = entry["fatigue"] > 70
            gain = config.career_fatigue_per_match
            if gains is not None:
                gain = gains.get(card_id, gain)
            entry["fatigue"] = min(100, entry["fatigue"] + gain)
            injury_pct = club_base_service.injury_chance(config.career_injury_chance_pct, base_fx or {})
            if rng.random() * 100 < injury_pct * (2 if tired else 1):
                entry["injured_until"] = round_index + 1 + rng.randint(1, 2)
                report["injured"].append(name)
            # Discipline: a straight red, or the Nth yellow, = one round out.
            if rng.random() * 100 < config.career_red_chance_pct * card_mult:
                entry["suspended_until"] = round_index + 2
                report["red"].append(name)
            elif rng.random() * 100 < config.career_yellow_chance_pct * card_mult:
                entry["yellows"] += 1
                report["yellow"].append(name)
                if entry["yellows"] >= config.career_yellows_for_ban:
                    entry["yellows"] = 0
                    entry["suspended_until"] = round_index + 2
                    report["suspended"].append(name)
            # Form for the next match: a win lifts, a defeat can drag down.
            roll = rng.random()
            if own > opp and roll < 0.5:
                entry["form"] = config.career_form_max if roll < 0.15 else 1
            elif own < opp and roll < 0.4:
                entry["form"] = -1
            else:
                entry["form"] = 0
            if entry["form"] > 0:
                report["form_up"].append(name)
            elif entry["form"] < 0:
                report["form_down"].append(name)
        else:
            recovery = config.career_fatigue_recovery + int((base_fx or {}).get("recovery", 0))
            entry["fatigue"] = max(0, entry["fatigue"] - recovery)
            entry["form"] = 0
        condition[str(card_id)] = entry
    part.condition = condition
    return report


def _report_line(report: dict) -> str:
    parts = []
    if report["red"]:
        parts.append("красная: " + ", ".join(report["red"]))
    if report["suspended"]:
        parts.append("перебор жёлтых: " + ", ".join(report["suspended"]))
    if report["injured"]:
        parts.append("травма: " + ", ".join(report["injured"]))
    return ("\n" + "; ".join(parts).capitalize()) if parts else ""


async def _finish(db: AsyncSession, season: CareerSeason, config) -> None:
    table = standings(season.state)
    place_of = {row["team_index"]: n + 1 for n, row in enumerate(table)}
    if season.division is not None:
        pct = int(_division_setting(config, "career_division_reward_pct", season.division, 100))
        label = division_name(season.division, config)
    else:
        pct = (config.career_difficulty_reward_pct or [100, 150, 200])[DIFFICULTIES.index(season.difficulty)]
        label = DIFFICULTY_LABELS[season.difficulty]
    trophy = (await db.execute(
        select(TrophyDefinition).where(TrophyDefinition.code == "career_champion", TrophyDefinition.is_active.is_(True))
    )).scalar_one_or_none()
    for part in season.participants:
        if part.status != "accepted":
            continue
        place = place_of[part.team_index]
        part.final_place = place
        rewards = config.career_place_rewards or []
        base = int(rewards[place - 1]) if place - 1 < len(rewards) else 0
        coins = await _credit(db, part.user_id, base * pct // 100, f"Карьера: {place} место", season.id)
        part.coins_earned += coins
        if place == 1 and trophy is not None:
            db.add(UserTrophy(
                user_id=part.user_id, trophy_definition_id=trophy.id,
                message=f"Сезон карьеры ({label})",
            ))
        move = ""
        if part.division is not None:
            part.next_division = division_after(part.division, place, config)
            profile = await get_profile(db, part.user_id, config)
            profile.seasons_played += 1
            rep = 0
            if place == 1:
                profile.titles += 1
                rep += int(config.career_rep_title)
            if part.next_division < part.division:
                profile.promotions += 1
                rep += int(config.career_rep_promotion)
                move = f"\nПовышение: следующий сезон — {division_name(part.next_division, config)}"
            elif part.next_division > part.division:
                rep += int(config.career_rep_relegation)
                move = f"\nВылет: следующий сезон — {division_name(part.next_division, config)}"
            objective_met = False
            if part.ambition in AMBITIONS:
                i = AMBITIONS.index(part.ambition)
                target = ambition_target(part.ambition, season.division or part.division, config)
                if place <= target["place"]:
                    objective_met = True
                    profile.objectives_met += 1
                    rep += int((config.career_ambition_rep_success or [0, 0, 0])[i])
                    bonus = base * pct // 100 * int((config.career_ambition_bonus_pct or [0, 0, 0])[i]) // 100
                    extra = await _credit(db, part.user_id, bonus, "Карьера: задача руководства", season.id)
                    part.coins_earned += extra
                    move += f"\nЗадача «{target['label']}» выполнена" + (f": +{extra} монет" if extra else "")
                else:
                    rep += int((config.career_ambition_rep_fail or [0, 0, 0])[i])
                    move += f"\nЗадача «{target['label']}» провалена"
            rep = club_base_service.reputation_gain(rep, part.base_effects or {})  # «Клубная база» media centre
            profile.reputation = max(0, profile.reputation + rep)
            profile.division = part.next_division
            if rep:
                move += f"\nРепутация: {'+' if rep > 0 else ''}{rep}"
            if _tactics_version(season.state) >= tactics.TACTICS_VERSION:
                new = achievements.record_season(
                    profile, place=place, division=part.division, division_label=division_name(part.division, config),
                    promoted=part.next_division < part.division, objective_met=objective_met,
                    cup_won=(season.state.get("cup") or {}).get("winner") == part.team_index,
                    unbeaten="L" not in _team_form_all(season.state, part.team_index), season_id=season.id,
                )
                move += await _grant_achievements(db, part, new, config, season.id)
        await notify(
            db, part.user_id, NotificationType.career_season_finished, f"Сезон карьеры завершён: {place} место",
            f"Награда: {coins} монет" + (" и трофей «Чемпион карьеры»" if place == 1 and trophy else "") + move,
            related_object_type="career_season", related_object_id=season.id,
        )
    season.status = "finished"
    season.finished_at = datetime.now(timezone.utc)
    if season.division is not None:
        renewing = []
        for part in season.participants:
            if part.status != "accepted" or part.next_division is None:
                continue
            profile = await get_profile(db, part.user_id, config)
            league_service.plan_next_league(
                profile, table, season.state.get("teams") or [], season.division, part.next_division,
                lambda division, place: division_after(division, place, config),
            )
            renewing.append(part)
        await _create_next_season(db, renewing, season, config, season.finished_at)


async def resolve_due(db: AsyncSession, season_id: int, now: Optional[datetime] = None) -> int:
    """Plays every round whose time has come (and starts a pending season
    whose friend invite expired). Returns the number of rounds played."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    season = await _lock_season(db, season_id)
    played = 0
    if season.status == "pending" and season.invite_expires_at and ensure_aware(season.invite_expires_at) <= now:
        for part in season.participants:
            if part.status == "invited":
                part.status = "declined"
        await _activate(db, season, now, config)
    while season.status == "active" and season.rounds_played < ROUNDS:
        index = season.rounds_played
        at = _round_at(season, index)
        if at is None or at > now:
            break
        if _live_applies(season, config) and now < at + timedelta(minutes=int(config.career_halftime_minutes)):
            # Live match centre: the first half now, the second after the break.
            if ((season.state or {}).get("live") or {}).get("round") != index:
                await _play_round(db, season, index, config, live=True)
            break
        await _play_round(db, season, index, config)
        played += 1
    await db.commit()
    return played


# How long after the second half kicks off it is "on air" (its show is
# 1.5-2.5 minutes; a margin for coming in late).
SECOND_HALF_ON_AIR = timedelta(minutes=6)


def _second_half_at(season: CareerSeason, round_index: int, config) -> Optional[datetime]:
    """When the second half of a live round kicked off (the end of its
    break), or None when the round wasn't played live."""
    at = _round_at(season, round_index)
    if at is None or not _live_applies(season, config):
        return None
    return at + timedelta(minutes=int(config.career_halftime_minutes))


def _second_half_out(season: CareerSeason, me: CareerParticipant, config) -> Optional[dict]:
    """My match whose second half is on air right now (just played after the
    break): the career screen offers to watch it live."""
    r = season.rounds_played - 1
    results = (season.state or {}).get("results") or []
    if r < 0 or r >= len(results):
        return None
    at = _second_half_at(season, r, config)
    now = datetime.now(timezone.utc)
    if at is None or not (at <= now < at + SECOND_HALF_ON_AIR):
        return None
    for index, m in enumerate(results[r]):
        if me.team_index in (m["home"], m["away"]) and m.get("lineups"):
            return {"round": r, "match_index": index, "second_half_at": at.isoformat()}
    return None


def _live_applies(season: CareerSeason, config) -> bool:
    return (bool(config.career_live_enabled) and _tactics_version(season.state) >= tactics.TACTICS_VERSION
            and any(p.status == "accepted" for p in season.participants))


def _live_record(match, run_h, run_a, home: int, away: int) -> dict:
    """First half of a live match: score and events up to HALF_TIME and each
    human-relevant side as it went into the break."""
    first = [e for e in match.event_log if (e.get("minute") or 0) <= tactics.HALF_TIME]
    goals = {"a": 0, "b": 0}
    for e in first:
        if e.get("event_type") == "goal" and e.get("team") in goals:
            goals[e["team"]] += 1
    sides = {}
    for index, runner, own, opp in ((home, run_h, goals["a"], goals["b"]), (away, run_a, goals["b"], goals["a"])):
        if runner.snapshot is None:
            runner._take_snapshot(own, opp)
        sides[str(index)] = runner.snapshot
    return {"home": home, "away": away, "hs": goals["a"], "as": goals["b"], "events": first, "sides": sides}


REMINDER_WINDOW = timedelta(minutes=60)


async def _reminder_notes(db: AsyncSession, season: CareerSeason, part: CareerParticipant, index: int) -> list[str]:
    """What to check before this round: holes in the XI, a cup tie the same
    evening without rotation, off-season choices still open."""
    notes = []
    state = season.state or {}
    cards = await _career_cards(db, part.user_id)
    by_id = {c.id: c for c in cards}
    xi = resolve_lineup(part, by_id, index, [c for c in cards if _usable(c)],
                        fill_any_position=_tactics_version(state) >= tactics.TACTICS_VERSION)
    holes = [w for w in _squad_warnings(part, by_id, index, xi) if w["level"] == "critical"]
    if holes:
        notes.append(f"⚠️ Дыры в составе: {len(holes)} — кто-то сыграет не по амплуа.")
    out_xi = [by_id[cid].player.display_name for cid in (part.lineup or {}).values()
              if cid in by_id and _is_out(part, cid, index)]
    if out_xi:
        notes.append(f"🚑 Не сыграют: {', '.join(out_xi[:3])} — замени в составе.")
    cup = state.get("cup") or {}
    if cup and index in CUP_AFTER_ROUNDS and cup.get("winner") is None:
        k = CUP_AFTER_ROUNDS.index(index)
        ties = (cup.get("rounds") or [])[k]["ties"] if k < len(cup.get("rounds") or []) else []
        mine = any(part.team_index in tie for tie in ties)
        if mine and not (cup.get("rotation") or {}).get(str(part.team_index)):
            notes.append("🏆 Вечером ещё и кубок — включи ротацию, чтобы не загнать основу.")
    if index == 0 and _offseason_of(state, part.team_index) and not part.camp:
        notes.append("🏕 Сборы ещё не выбраны.")
    return notes


async def send_reminders(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """"Скоро тур — проверь состав": one notification per human per round,
    for rounds starting within REMINDER_WINDOW, with what needs attention
    (holes, the cup evening, the off-season). The evening before an
    off-season's first round: one more about the camp and squad. The bot
    calls this ~30 min before each slot; state["reminded"] /
    state["reminded_offseason"] keep it to one each."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    if not config.career_reminders_enabled:
        return 0
    ids = (await db.execute(select(CareerSeason.id).where(CareerSeason.status == "active"))).scalars().all()
    sent = 0
    for season_id in ids:
        season = await _lock_season(db, season_id)
        index = season.rounds_played
        at = _round_at(season, index) if season.status == "active" else None
        state = copy.deepcopy(season.state or {})
        reminded = list(state.get("reminded") or [])
        changed = False
        if (at is not None and index == 0 and state.get("offseason") and not state.get("reminded_offseason")
                and now + REMINDER_WINDOW < at <= now + OFFSEASON_REMINDER_WINDOW):
            when = at.astimezone(app_timezone()).strftime("%d.%m в %H:%M")
            for part in season.participants:
                if part.status != "accepted":
                    continue
                await notify(
                    db, part.user_id, NotificationType.career_reminder, "Предсезонка: скоро старт сезона",
                    f"Первый тур — {when}. " + ("Сборы ещё не выбраны. " if not part.camp else "")
                    + "Проверь заявку, цель руководства и сыграй товарищеский матч.",
                    related_object_type="career_season", related_object_id=season.id,
                )
                sent += 1
            state["reminded_offseason"] = True
            changed = True
        if at is not None and index not in reminded and now < at <= now + REMINDER_WINDOW:
            teams = state["teams"]
            minutes = max(1, round((at - now).total_seconds() / 60))
            for part in season.participants:
                if part.status != "accepted":
                    continue
                match = next(m for m in state["fixtures"][index] if part.team_index in m)
                opponent = teams[match[1] if match[0] == part.team_index else match[0]]["name"]
                notes = await _reminder_notes(db, season, part, index)
                await notify(
                    db, part.user_id, NotificationType.career_reminder, f"Карьера: тур {index + 1} через {minutes} мин",
                    f"Соперник — «{opponent}». " + (" ".join(notes) if notes else
                                                     "Проверь состав: усталость, травмы и дисквалификации."),
                    related_object_type="career_season", related_object_id=season.id,
                )
                sent += 1
            state["reminded"] = reminded + [index]
            changed = True
        if changed:
            season.state = state
            flag_modified(season, "state")
        await db.commit()
    return sent


OFFSEASON_REMINDER_WINDOW = timedelta(hours=20)


def _week_key(now: datetime) -> str:
    year, week, _ = now.astimezone(app_timezone()).isocalendar()
    return f"{year}-W{week:02d}"


async def _digest_for(db: AsyncSession, profile: CareerProfile, now: datetime, config) -> Optional[str]:
    """Last 7 days of a coach's career as text, None if nothing was played."""
    since = now - timedelta(days=7)
    parts = (await db.execute(
        select(CareerParticipant).join(CareerSeason, CareerSeason.id == CareerParticipant.season_id)
        .where(CareerParticipant.user_id == profile.user_id, CareerParticipant.status == "accepted",
               CareerSeason.status.in_(("active", "finished")), CareerSeason.created_at >= now - timedelta(days=30))
        .options(joinedload(CareerParticipant.season))
    )).scalars().unique().all()
    w = d = lose = gf = ga = 0
    scorers: dict[str, int] = {}
    place_line = None
    for part in parts:
        state = part.season.state or {}
        schedule = state.get("schedule") or []
        for r, results in enumerate(state.get("results") or []):
            at = datetime.fromisoformat(schedule[r]) if r < len(schedule) else None
            if at is None or not (since <= at <= now):
                continue
            m = next((m for m in results if part.team_index in (m["home"], m["away"])), None)
            if m is None:
                continue
            home = m["home"] == part.team_index
            own, opp = (m["hs"], m["as"]) if home else (m["as"], m["hs"])
            gf, ga = gf + own, ga + opp
            w, d, lose = w + (own > opp), d + (own == opp), lose + (own < opp)
            side = "a" if home else "b"
            for e in m.get("events") or []:
                if e.get("event_type") == "goal" and e.get("team") == side:
                    name = (e.get("payload") or {}).get("shooter")
                    if name:
                        scorers[name] = scorers.get(name, 0) + 1
        if part.season.status == "active" and state.get("teams"):
            table = standings(state)
            place = next((n + 1 for n, row in enumerate(table) if row["team_index"] == part.team_index), None)
            if place and part.season.division is not None:
                place_line = f"Лига: {place}-е место · {division_name(part.season.division, config)}"
    if w + d + lose == 0:
        return None
    data = achievements.data_of(profile)
    lines = [f"Матчи: {w + d + lose} · {w}В {d}Н {lose}П · голы {gf}:{ga}"]
    if place_line:
        lines.append(place_line)
    if scorers:
        name, goals = max(scorers.items(), key=lambda x: (x[1], x[0]))
        lines.append(f"Лучший бомбардир: {name} — {goals}")
    prev_rep = (data.get("digest") or {}).get("reputation")
    delta = profile.reputation - prev_rep if prev_rep is not None else None
    lines.append(f"Репутация: {profile.reputation}" + (f" ({'+' if delta >= 0 else ''}{delta})" if delta else ""))
    fresh = [code for code, at in data["unlocked"].items() if datetime.fromisoformat(at) >= since]
    if fresh:
        lines.append(f"Достижения: {achievements.titles_text(fresh)}")
    return "\n".join(lines)


async def send_weekly_digests(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """«Неделя в карьере»: once per ISO week (the first career slot of the
    week fires it) to every coach who played in the last 7 days."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    if not config.career_digest_enabled or not config.career_enabled:
        return 0
    week = _week_key(now)
    profiles = (await db.execute(
        select(CareerProfile).where(CareerProfile.last_active_at >= now - timedelta(days=30))
    )).scalars().all()
    sent = 0
    for profile in profiles:
        data = achievements.data_of(profile)
        if (data.get("digest") or {}).get("week") == week:
            continue
        text = await _digest_for(db, profile, now, config)
        data["digest"] = {"week": week, "reputation": profile.reputation}
        profile.achievements = data
        if text:
            await notify(db, profile.user_id, NotificationType.career_digest, "📊 Карьера: итоги недели", text)
            sent += 1
        await db.commit()
    return sent


async def resolve_all_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    ids = (await db.execute(
        select(CareerSeason.id).where(
            or_(CareerSeason.status == "active",
                (CareerSeason.status == "pending") & (CareerSeason.invite_expires_at <= now)),
        )
    )).scalars().all()
    total = 0
    for season_id in ids:
        total += await resolve_due(db, season_id, now)
    return total


# --- read model -------------------------------------------------------------------

async def get_view(db: AsyncSession, user: User) -> dict:
    """The player's current (or most recently finished) season, after
    catching up on due rounds."""
    part = await _current_participation(db, user.id)
    if part is not None:
        await resolve_due(db, part.season_id)
    part = (await db.execute(
        select(CareerParticipant).where(CareerParticipant.user_id == user.id, CareerParticipant.status != "declined")
        .order_by(CareerParticipant.id.desc()).limit(1)
    )).scalar_one_or_none()
    config = await get_config(db)
    profile = await get_profile(db, user.id, config)
    profile.last_active_at = datetime.now(timezone.utc)
    await db.commit()
    base = {"enabled": config.career_enabled, "profile": _profile_out(profile, config), "difficulties": [
        {"code": d, "label": DIFFICULTY_LABELS[d], "reward_pct": (config.career_difficulty_reward_pct or [100, 150, 200])[i]}
        for i, d in enumerate(DIFFICULTIES)
    ], "place_rewards": config.career_place_rewards, "slots": [f"{h:02d}:{m:02d}" for h, m in CAREER_SLOTS],
        # The same slots as today's absolute times, so the client can show them
        # in the player's own time zone (the calendar does the same).
        "slot_times": _todays_slot_times(),
        # Where the next season would be played (no manual difficulty).
        "division": _division_info(await current_division(db, user.id, config), config),
        "divisions": [_division_info(d, config) for d in range(1, division_count(config) + 1)],
        "tactics_catalog": tactics_catalog(config)}
    if part is None:
        return {**base, "season": None}
    season = await db.get(CareerSeason, part.season_id)
    await db.refresh(season)
    if season.status == "cancelled" or (season.status == "finished" and season.finished_at and
                                         ensure_aware(season.finished_at) < datetime.now(timezone.utc) - timedelta(days=3)):
        return {**base, "season": None}
    return {**base, "season": await _season_out(db, season, part)}


async def _season_out(db: AsyncSession, season: CareerSeason, me: CareerParticipant) -> dict:
    state = season.state or {}
    teams = state.get("teams") or []
    users = {p.user_id: await db.get(User, p.user_id) for p in season.participants}
    out = {
        "id": season.id, "status": season.status, "difficulty": season.difficulty,
        "difficulty_label": DIFFICULTY_LABELS[season.difficulty],
        "division": None, "next_division": None,
        "rounds_played": season.rounds_played, "total_rounds": ROUNDS,
        "schedule": state.get("schedule") or [],
        "next_round_at": (state.get("schedule") or [None] * ROUNDS)[season.rounds_played] if season.rounds_played < ROUNDS and state.get("schedule") else None,
        "invite_expires_at": season.invite_expires_at,
        "is_creator": season.creator_id == me.user_id,
        "my_status": me.status,
        "my_team_index": me.team_index,
        "final_place": me.final_place, "coins_earned": me.coins_earned,
        "participants": [
            {"user_id": p.user_id, "name": (users[p.user_id].first_name or users[p.user_id].username or "Игрок") if users.get(p.user_id) else "Игрок",
             "status": p.status, "team_index": p.team_index}
            for p in season.participants
        ],
        "teams": [
            {"index": t["index"], "name": t["name"], "is_bot": t.get("user_id") is None, "user_id": t.get("user_id"),
             "strength": round(sum(p["rating"] for p in t["players"]) / len(t["players"])) if t.get("players") else None}
            for t in teams
        ],
        "table": standings(state) if teams else [],
        "rounds": [],
        "squad": [], "lineup": {}, "slots": [],
        "formation": me.formation, "mentality": me.mentality, "playstyle": me.playstyle,
        "tactic": _my_tactic(me), "squad_size": len(me.squad_card_ids or []),
        "tactics_version": _tactics_version(state),
        "scouting": None, "familiarity": None, "match_plan": me.match_plan, "plan_limits": {},
        "ambition": me.ambition, "ambitions": [], "training": me.training, "trainings": training_options(),
        "cup": None, "offseason": None, "summary": None,
        "set_pieces": {**tactics.DEFAULT_SET_PIECES, **(me.set_pieces or {})}, "squad_warnings": [],
        "roles": me.roles or {}, "live": None, "plan_hints": [],
    }
    if season.division is not None:
        config = await get_config(db)
        out["division"] = _division_info(season.division, config)
        out["ambitions"] = ambition_options(season.division, config)
        out["cup"] = _cup_out(state, me, config)
        out["offseason"] = await _offseason_out(db, season, me, config)
        if season.status == "finished":
            cards_now = {c.id: c for c in await _career_cards(db, me.user_id)}
            out["summary"] = _season_summary(state, me, {cid: c.player.display_name for cid, c in cards_now.items()})
        if me.next_division is not None:
            out["next_division"] = _division_info(me.next_division, config)
    results = state.get("results") or []
    for r, fixtures in enumerate(state.get("fixtures") or []):
        played = results[r] if r < len(results) else None
        out["rounds"].append({
            "index": r, "at": (state.get("schedule") or [None] * ROUNDS)[r],
            "matches": [
                {"home": h, "away": a,
                 "hs": played[i]["hs"] if played else None, "as": played[i]["as"] if played else None,
                 "has_events": bool(played and played[i].get("events"))}
                for i, (h, a) in enumerate(fixtures)
            ],
            # Viewer's own after-match report: cards, injuries, form.
            "report": ((state.get("reports") or {}).get(str(r)) or {}).get(str(me.team_index)),
        })
    if me.status == "accepted" and season.status == "active" and season.rounds_played < ROUNDS:
        config = await get_config(db)
        out["scouting"] = _scouting(season, me, config, await get_profile(db, me.user_id, config))
        if out["tactics_version"] >= tactics.TACTICS_VERSION:
            out["familiarity"] = {
                "stored_pct": me.familiarity / 10,
                "current_pct": tactics.familiarity_for(
                    me.familiarity, me.familiar_formation, me.familiar_tactic, me.formation, _my_tactic(me), config,
                ) / 10,
                "max_pct": config.career_familiarity_max_tenths / 10,
                "step_pct": config.career_familiarity_step_tenths / 10,
                "keep_pct": config.career_familiarity_keep_pct,
                "axis_keep_pct": config.career_familiarity_axis_keep_pct,
                "last_formation": me.familiar_formation, "last_tactic": me.familiar_tactic,
            }
            out["plan_limits"] = {"rules": config.career_max_plan_rules, "subs": config.career_max_substitutions}
    if me.status == "accepted":
        cards = await _career_cards(db, me.user_id)
        by_id = {c.id: c for c in cards}
        next_round = min(season.rounds_played, ROUNDS - 1)
        xi = resolve_lineup(
            me, by_id, next_round, [c for c in cards if _usable(c)], fill_any_position=bool(out["tactics_version"]),
        )
        out["lineup"] = {slot.code: card.id for card, slot in xi}
        out["squad_warnings"] = _squad_warnings(me, by_id, next_round, xi)
        if out["tactics_version"] >= tactics.TACTICS_VERSION and season.status == "active":
            config = await get_config(db)
            out["live"] = _live_out(season, me, by_id, config)
            out["second_half"] = None if out["live"] else _second_half_out(season, me, config)
            out["plan_hints"] = _plan_hints(me, xi, config, out["scouting"])
        # Chemistry of the XI that would play the next round, under the
        # season's frozen rules (tactics seasons only).
        rules = chemistry_service.rules_from_dict(state.get("chemistry_rules")) if out["tactics_version"] else None
        result = (
            chemistry_service.compute_chemistry(xi, me.formation, rules, slot_count=len(get_formation_slots(me.formation)))
            if rules is not None and xi else None
        )
        out["chemistry"] = chemistry_service.to_out(
            result, rules, live_enabled=chemistry_service.active_rules(await get_config(db)) is not None,
        )
        out["slots"] = [{"code": s.code, "category": s.category, "ideal_position": s.ideal_position.value}
                        for s in get_formation_slots(me.formation)]
        from app.schemas.card import UserCardOut

        for card_id in _squad_ids(me, by_id):
            card = by_id.get(card_id)
            cond = _condition(me, card_id)
            mine = getattr(card, "is_my_player", False)
            out["squad"].append({
                "card": UserCardOut.model_validate(card) if card and not mine else None,
                "my_player": (
                    {"name": card.player.display_name, "position": card.player.position.value, "rating": card.player.rating,
                     "club": card.player.club, "country": card.player.country}
                    if mine else None
                ),
                "card_id": card_id,
                "fatigue": cond["fatigue"],
                "injured_rounds": max(0, cond["injured_until"] - next_round),
                "suspended_rounds": max(0, cond["suspended_until"] - next_round),
                "yellows": cond["yellows"],
                "form": cond["form"],
                "owned": card is not None,
            })
    return out


FORM_MATCHES = 5


def _team_form_all(state: dict, team_index: int) -> list[str]:
    form = []
    for round_results in state.get("results") or []:
        for m in round_results:
            if team_index in (m["home"], m["away"]):
                own, opp = (m["hs"], m["as"]) if m["home"] == team_index else (m["as"], m["hs"])
                form.append("W" if own > opp else "D" if own == opp else "L")
    return form


async def _grant_achievements(db: AsyncSession, part: CareerParticipant, codes: list[str], config, season_id: int) -> str:
    """Coins for newly unlocked achievements (counted in the season's
    earnings); the line for the notification."""
    if not codes:
        return ""
    amount = int(config.career_achievement_reward) * len(codes)
    credited = await _credit(db, part.user_id, amount, "Карьера: достижения", season_id) if amount else 0
    part.coins_earned += credited
    return f"\nДостижения: {achievements.titles_text(codes)}" + (f" · +{credited} монет" if credited else "")


async def leaderboard(db: AsyncSession, user: User, division: Optional[int] = None, limit: int = 50) -> dict:
    """Coaches by reputation (then titles, promotions), overall or within
    the division their next season is played in."""
    config = await get_config(db)
    query = select(CareerProfile, User).join(User, User.id == CareerProfile.user_id)
    if division is not None:
        query = query.where(CareerProfile.division == division)
    query = query.order_by(CareerProfile.reputation.desc(), CareerProfile.titles.desc(),
                           CareerProfile.promotions.desc(), CareerProfile.id)
    rows = (await db.execute(query.limit(limit))).all()

    def row(n: int, profile: CareerProfile, u: User) -> dict:
        data = achievements.data_of(profile)
        return {
            "rank": n, "user_id": u.id, "name": u.first_name or u.username or "Тренер",
            "division": profile.division, "division_name": division_name(profile.division, config),
            "reputation": profile.reputation, "level": reputation_level(profile.reputation, config)["name"],
            "titles": profile.titles, "promotions": profile.promotions, "seasons": profile.seasons_played,
            "trophies": len(data["trophies"]), "achievements": len(data["unlocked"]), "is_me": u.id == user.id,
        }

    out = [row(n + 1, profile, u) for n, (profile, u) in enumerate(rows)]
    me = None
    if not any(r["is_me"] for r in out):
        mine = (await db.execute(select(CareerProfile).where(CareerProfile.user_id == user.id))).scalar_one_or_none()
        if mine is not None and (division is None or mine.division == division):
            ahead = select(func.count()).select_from(CareerProfile).where(CareerProfile.reputation > mine.reputation)
            if division is not None:
                ahead = ahead.where(CareerProfile.division == division)
            me = row(int((await db.execute(ahead)).scalar_one()) + 1, mine, user)
    return {"division": division, "rows": out, "me": me,
            "divisions": [_division_info(d, config) for d in range(1, division_count(config) + 1)]}


def _team_form(state: dict, team_index: int) -> list[str]:
    """Last FORM_MATCHES results of a team, oldest first: W / D / L."""
    form = []
    for round_results in state.get("results") or []:
        for m in round_results:
            if team_index not in (m["home"], m["away"]):
                continue
            own, opp = (m["hs"], m["as"]) if m["home"] == team_index else (m["as"], m["hs"])
            form.append("W" if own > opp else "D" if own == opp else "L")
    return form[-FORM_MATCHES:]


def _scouting(season: CareerSeason, me: CareerParticipant, config, profile: Optional[CareerProfile] = None) -> Optional[dict]:
    """The next opponent as far as it is knowable: the tactic it actually
    played last (or its season set-up before round 1 — a friend's is hidden
    until played), its form, and the counter hint for my saved style
    against it, from the same table the engine applies."""
    state = season.state or {}
    fixtures = state.get("fixtures") or []
    round_index = season.rounds_played
    if round_index >= len(fixtures):
        return None
    pair = next((m for m in fixtures[round_index] if me.team_index in m), None)
    if pair is None:
        return None
    opp_index = pair[1] if pair[0] == me.team_index else pair[0]
    team = state["teams"][opp_index]
    is_bot = team.get("user_id") is None
    history = (state.get("played_tactics") or {}).get(str(opp_index)) or []
    v1 = _tactics_version(state) >= tactics.TACTICS_VERSION
    if history:
        seen, source = history[-1], "last_match"
    elif is_bot:
        seen, source = team, "season_start"
    else:
        seen, source = {}, "season_start"
    their = tactics.tactic_for(seen.get("tactic"), seen.get("playstyle")) if seen else None
    my_history = (state.get("played_tactics") or {}).get(str(me.team_index)) or []
    my_last = tactics.tactic_for(my_history[-1].get("tactic"), my_history[-1].get("playstyle")) if my_history else None
    adaptive = v1 and is_bot and season.difficulty in ("pro", "legend")
    star = None
    if v1 and is_bot and team.get("players"):
        outfield = [(c, slot) for c, slot in _bot_cards(team, round_index, config) if slot.category != "GK"]
        if outfield:
            c, slot = max(outfield, key=lambda x: (x[0].player.rating, -x[0].id))
            star = {"player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
                    "position": c.player.position.value}
    marking = me.marking if (me.marking or {}).get("round") == round_index else None
    mine = _my_tactic(me)
    threat = None
    if adaptive and my_last:
        # What a counter-picking bot would choose against my last played tactic.
        code = max(tactics.PRESETS, key=lambda c: tactics.matchup_report(tactics.PRESETS[c], my_last, config)["score"])
        threat = {"preset": code, "tactic": tactics.PRESETS[code]}
    return {
        "head_to_head": league_service.head_to_head(profile, team.get("club_id")) if is_bot else None,
        "round_index": round_index, "opponent_index": opp_index, "opponent_name": team["name"], "is_bot": is_bot,
        "strength": round(sum(p["rating"] for p in team["players"]) / len(team["players"])) if team.get("players") else None,
        "formation": seen.get("formation"), "mentality": seen.get("mentality"),
        "tactic": their if v1 else None, "preset": tactics.preset_of(their) if v1 and their else None,
        "playstyle": seen.get("playstyle"),
        "source": source, "form": _team_form(state, opp_index),
        "matchup": tactics.matchup_report(mine, their, config) if v1 and their else None,
        "win_pct": tactics.preset_win_pct(tactics.preset_of(mine), tactics.preset_of(their)) if v1 and their else None,
        "adaptive": adaptive, "my_last_tactic": my_last if adaptive else None, "threat": threat,
        "star": star, "marking": marking, "marks_you": v1 and is_bot and season.difficulty == "legend",
    }


def matchup_preview(season: CareerSeason, me: CareerParticipant, tactic: dict, config) -> Optional[dict]:
    """Matchup report for a tactic the player is still choosing (not saved
    yet) against the next opponent's known tactic."""
    scouting = _scouting(season, me, config)
    if not scouting or not scouting.get("tactic"):
        return None
    return tactics.matchup_report(tactic, scouting["tactic"], config)


async def preview(db: AsyncSession, user: User, tactic: dict) -> Optional[dict]:
    part = await _current_participation(db, user.id)
    if part is None or part.status != "accepted":
        raise NotFoundError("Нет активного сезона")
    try:
        tactic = tactics.clean_tactic(tactic)
    except tactics.TacticError as exc:
        raise ConflictError(str(exc)) from exc
    season = await db.get(CareerSeason, part.season_id)
    return matchup_preview(season, part, tactic, await get_config(db))


def tactics_catalog(config) -> dict:
    """Axes, values, presets and interactions for the tactics UI — the
    client never keeps its own copy of these tables."""
    return {
        "roles": [
            {"group": g, "label": spec["label"], "positions": list(spec["positions"]),
             "values": [{"value": v, "label": tactics.ROLE_LABELS[g][v], "hint": tactics.ROLE_HINTS[g][v]}
                        for v in spec["values"]]}
            for g, spec in tactics.ROLE_GROUPS.items()
        ],
        "axes": [{"key": axis, "label": tactics.AXIS_LABELS[axis],
                  "values": [{"value": v, "label": tactics.VALUE_LABELS[axis][v], "hint": tactics.VALUE_HINTS[axis][v]}
                             for v in values]}
                 for axis, values in tactics.AXES.items()],
        "presets": [{"code": code, "label": tactics.PRESET_LABELS[code], "tactic": axes}
                    for code, axes in tactics.PRESETS.items()],
        "interactions": [{"id": ix["id"], "label": ix["label"], "base": bool(ix.get("base"))} for ix in tactics.INTERACTIONS],
        "set_pieces": {
            "routines": [{"value": k, "label": v} for k, v in tactics.CORNER_ROUTINES.items()],
            "defences": [{"value": k, "label": v} for k, v in tactics.SET_PIECE_DEFENCES.items()],
            "beats": tactics.ROUTINE_BEATS,
        },
    }


async def cup_match_events(db: AsyncSession, user: User, season_id: int, round_index: int, tie_index: int) -> dict:
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    cup = (season.state or {}).get("cup") or {}
    rounds = cup.get("rounds") or []
    if round_index >= len(rounds) or tie_index >= len(rounds[round_index].get("results") or []):
        raise NotFoundError("Матч ещё не сыгран")
    res = rounds[round_index]["results"][tie_index]
    me = next(p for p in season.participants if p.user_id == user.id)
    my_side = "a" if res["a"] == me.team_index else "b" if res["b"] == me.team_index else None
    return {
        "home_name": _cup_team(season.state, res["a"])["name"], "away_name": _cup_team(season.state, res["b"])["name"],
        "home_score": res["sa"], "away_score": res["sb"], "events": res.get("events") or [],
        "analysis": (res.get("analysis") or {}).get(str(me.team_index)) if my_side else None,
        "my_side": my_side, "pens": res.get("pens"), "kicks": res.get("kicks"),
    }


async def match_events(db: AsyncSession, user: User, season_id: int, round_index: int, match_index: int) -> dict:
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    results = (season.state or {}).get("results") or []
    if round_index >= len(results) or match_index >= len(results[round_index]):
        raise NotFoundError("Матч ещё не сыгран")
    m = results[round_index][match_index]
    teams = season.state["teams"]
    me = next(p for p in season.participants if p.user_id == user.id)
    my_side = "a" if m["home"] == me.team_index else "b" if m["away"] == me.team_index else None
    return {
        "home_name": teams[m["home"]]["name"], "away_name": teams[m["away"]]["name"],
        "home_score": m["hs"], "away_score": m["as"], "events": m.get("events") or [],
        # Only the viewer's own analysis (their plan/instructions stay private).
        "analysis": (m.get("analysis") or {}).get(str(me.team_index)) if my_side else None,
        "my_side": my_side,
    }


async def match_replay(db: AsyncSession, user: User, season_id: int, round_index: int, match_index: int) -> dict:
    """2D replay of a league match with a human (career_replay_service):
    the whole match once played; during the live break only the first half
    (the second one is built after the coach's half-time orders)."""
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    state = season.state or {}
    teams = state.get("teams") or []
    me = next(p for p in season.participants if p.user_id == user.id)
    results = state.get("results") or []
    live = state.get("live") or {}
    if round_index < len(results) and match_index < len(results[round_index]):
        m = results[round_index][match_index]
        events, lineups, halves, hs, as_ = m.get("events"), m.get("lineups"), 2, m["hs"], m["as"]
        if lineups is None and m.get("tactics"):  # played before lineups were stored
            lineups = {side: {"formation": (m["tactics"].get(str(m[team])) or {}).get("formation"),
                              "tactic": (m["tactics"].get(str(m[team])) or {}).get("tactic")}
                       for side, team in (("a", "home"), ("b", "away"))}
        # A live round's second half: the viewer can follow it in real time
        # from this moment (its frames still come all at once).
        at = _second_half_at(season, round_index, await get_config(db)) if m.get("lineups") else None
        second_half_at = at.isoformat() if at else None
    elif live.get("round") == round_index and str(match_index) in (live.get("matches") or {}):
        m = live["matches"][str(match_index)]
        events, lineups, halves, hs, as_ = m["events"], m.get("lineups"), 1, m["hs"], m["as"]
        second_half_at = live["second_half_at"]
    else:
        raise NotFoundError("Матч ещё не сыгран")
    my_side = "a" if m["home"] == me.team_index else "b" if m["away"] == me.team_index else None
    return _replay_out(
        teams[m["home"]]["name"], teams[m["away"]]["name"], hs, as_, events, lineups, my_side,
        _match_seed(season.id, round_index, match_index), halves, second_half_at,
    )


def _replay_out(home_name: str, away_name: str, hs: int, as_: int, events, lineups, my_side, seed: int,
                halves: int = 2, second_half_at=None) -> dict:
    """The 2D replay payload of any career match (league, cup, friendly)."""
    if not events:
        raise NotFoundError("Для этого матча нет записи")
    return {
        "home_name": home_name, "away_name": away_name,
        "home_score": hs, "away_score": as_, "events": events, "my_side": my_side,
        "live": halves == 1, "second_half_at": second_half_at,
        "replay": career_replay.build_replay(seed, events, lineups, halves),
    }


# Replay seeds of cup ties and friendlies: apart from the league's
# (_match_seed with round indices far above a season's rounds).
CUP_SEED_ROUND, FRIENDLY_SEED_ROUND = 500, 900


async def cup_match_replay(db: AsyncSession, user: User, season_id: int, round_index: int, tie_index: int) -> dict:
    """2D replay of a cup tie with a human (the 90 minutes; a shoot-out is
    shown by the match page)."""
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    rounds = ((season.state or {}).get("cup") or {}).get("rounds") or []
    if round_index >= len(rounds) or tie_index >= len(rounds[round_index].get("results") or []):
        raise NotFoundError("Матч ещё не сыгран")
    res = rounds[round_index]["results"][tie_index]
    me = next(p for p in season.participants if p.user_id == user.id)
    my_side = "a" if res["a"] == me.team_index else "b" if res["b"] == me.team_index else None
    return _replay_out(
        _cup_team(season.state, res["a"])["name"], _cup_team(season.state, res["b"])["name"],
        res.get("sa", 0), res.get("sb", 0), res.get("events"), res.get("lineups"), my_side,
        _match_seed(season.id, CUP_SEED_ROUND + round_index, tie_index),
    )


async def friendly_replay(db: AsyncSession, user: User, season_id: int) -> dict:
    """2D replay of the coach's pre-season friendly."""
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    me = next(p for p in season.participants if p.user_id == user.id)
    friendly = _friendly_of(season.state or {}, me.team_index)
    if not friendly:
        raise NotFoundError("Товарищеский матч ещё не сыгран")
    return _replay_out(
        season.state["teams"][me.team_index]["name"], friendly["opponent"],
        friendly["home_score"], friendly["away_score"], friendly["events"], friendly.get("lineups"), "a",
        _match_seed(season.id, FRIENDLY_SEED_ROUND, me.team_index),
    )


async def invited_count(db: AsyncSession, user_id: int) -> int:
    return len((await db.execute(
        select(CareerParticipant.id).join(CareerSeason).where(
            CareerParticipant.user_id == user_id, CareerParticipant.status == "invited", CareerSeason.status == "pending",
        )
    )).all())


async def pending_invite(db: AsyncSession, user_id: int) -> Optional[dict]:
    row = (await db.execute(
        select(CareerParticipant, CareerSeason).join(CareerSeason).where(
            CareerParticipant.user_id == user_id, CareerParticipant.status == "invited", CareerSeason.status == "pending",
        ).options(joinedload(CareerParticipant.season)).limit(1)
    )).first()
    if row is None:
        return None
    _, season = row
    creator = await db.get(User, season.creator_id)
    return {
        "season_id": season.id, "difficulty_label": DIFFICULTY_LABELS[season.difficulty],
        "from_name": (creator.first_name or creator.username or "Друг") if creator else "Друг",
        "expires_at": season.invite_expires_at,
    }
