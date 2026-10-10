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
import copy
import random
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.card import UserCard
from app.models.career import CareerParticipant, CareerSeason, Friendship
from app.models.enums import NotificationType, Position, Rarity, TransactionType
from app.models.player import Player
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import tournament_match_engine, wallet_service
from app.services.auto_squad_service import SlotSpec, owned_cards, pick_cards
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES, build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS
from app.services.notification_service import notify
from app.services.player_tournament_simulation_service import _EngineCard, _engine_card

TEAMS = 8
ROUNDS = 14
SQUAD_SIZE = 16
# Local times of the two daily rounds. Keep in sync with bot/services/career_scheduler.py.
# 12:00 and 19:00 avoid the club (20:00) and player-tournament (10/15/21) slots.
CAREER_SLOTS: tuple[tuple[int, int], ...] = ((12, 0), (19, 0))
START_LEAD = timedelta(hours=1)  # time to set a lineup before round 1
INVITE_TTL = timedelta(hours=24)
DIFFICULTIES = ("amateur", "pro", "legend")
DIFFICULTY_LABELS = {"amateur": "Любитель", "pro": "Профи", "legend": "Легенда"}
BOT_FORMATIONS = ("4-3-3", "4-4-2", "3-5-2")
BOT_CLUB_NAMES = [
    "Северный Ветер", "Портовые Волки", "Динамо Рассвет", "Торпедо Восток", "Атлетик Лесной",
    "Горняк", "Спартак Заречье", "Метеор", "Звезда Юга", "Речники", "Сокол", "Буревестник",
]
ACTIVE_STATUSES = ("pending", "active")


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
    return min(99, card.player.rating + (card.diamond_rating_bonus or 0))


def _usable(card: UserCard) -> bool:
    return not card.is_locked_by_admin and not card.is_locked_in_trade


def pick_squad(cards: list[UserCard], formation: str = "4-3-3") -> list[int]:
    """Best XI for the formation plus a 5-card bench (one per line + the best
    remaining), distinct players only."""
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in get_formation_slots(formation)]
    xi = pick_cards(slots, cards, "tournament")
    if len(xi) < len(slots):
        raise ConflictError("Для карьеры нужно минимум 11 карточек, закрывающих все позиции схемы 4-3-3")
    chosen = [c.id for c in xi.values()]
    used_players = {c.player_id for c in xi.values()}
    pool = sorted(
        (c for c in cards if _usable(c) and c.id not in chosen and c.player_id not in used_players),
        key=lambda c: (-_effective(c), c.id),
    )
    for need in ("GK", "DEF", "MID", "FWD", None):
        for card in pool:
            if card.player_id in used_players:
                continue
            if need is None or card.player.position in CATEGORY_POSITIONS[need]:
                chosen.append(card.id)
                used_players.add(card.player_id)
                break
    return chosen[:SQUAD_SIZE]


_FRESH = {"fatigue": 0, "injured_until": 0, "suspended_until": 0, "yellows": 0, "form": 0}


def _condition(part: CareerParticipant, card_id: int) -> dict:
    return {**_FRESH, **(part.condition or {}).get(str(card_id), {})}


def _is_out(part: CareerParticipant, card_id: int, round_index: int) -> bool:
    """Injured or suspended for `round_index`."""
    cond = _condition(part, card_id)
    return cond["injured_until"] > round_index or cond["suspended_until"] > round_index


def resolve_lineup(
    part: CareerParticipant, cards_by_id: dict[int, UserCard], round_index: int, extra_cards: list[UserCard],
) -> list[tuple[UserCard, object]]:
    """The XI that plays `round_index`: the saved lineup where its cards are
    still owned, fit and in a legal slot, the gaps auto-filled from the
    squad (fresh players first), then — if the squad can't cover a slot —
    from the rest of the player's own collection."""
    slots = get_formation_slots(part.formation)
    squad = [cards_by_id[cid] for cid in part.squad_card_ids if cid in cards_by_id]
    available = [c for c in squad if _usable(c) and not _is_out(part, c.id, round_index)]
    by_id = {c.id: c for c in available}
    chosen: dict[str, UserCard] = {}
    used_players: set[int] = set()
    for slot in slots:
        card = by_id.get((part.lineup or {}).get(slot.code) or -1)
        if card and card.player.position in CATEGORY_POSITIONS[slot.category] and card.player_id not in used_players:
            chosen[slot.code] = card
            used_players.add(card.player_id)
    missing = [SlotSpec(s.code, s.category, s.ideal_position) for s in slots if s.code not in chosen]
    if missing:
        fresh = frozenset(c.id for c in available if _condition(part, c.id).get("fatigue", 0) < 60)
        pool = [c for c in available if c.player_id not in used_players]
        for code, card in pick_cards(missing, pool, "tournament", preferred_ids=fresh).items():
            chosen[code] = card
            used_players.add(card.player_id)
    missing = [SlotSpec(s.code, s.category, s.ideal_position) for s in slots if s.code not in chosen]
    if missing:
        pool = [c for c in extra_cards if c.player_id not in used_players and c.id not in part.squad_card_ids]
        chosen.update(pick_cards(missing, pool, "tournament"))
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
        }
        for c, slot in with_slots
    ]
    return side, lineup


def _bot_side(team: dict, round_index: int, config):
    slots = {s.code: s for s in get_formation_slots(team["formation"])}
    growth = config.career_bot_growth_tenths * round_index / 10
    with_slots = []
    for i, p in enumerate(team["players"]):
        player = SimpleNamespace(
            display_name=p["name"], position=Position(p["position"]), rating=min(99, round(p["rating"] + growth)),
            rarity=Rarity(p["rarity"]), club=p["club"], country=p["country"], attack_rating=None, defense_rating=None,
        )
        with_slots.append((_EngineCard(id=-(team["index"] * 100 + i + 1), player_id=p["player_id"], player=player), slots[p["slot"]]))
    side = build_side(with_slots, team["mentality"], team["playstyle"])
    lineup = [
        {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category}
        for c, slot in with_slots
    ]
    return side, lineup


async def _build_bots(db: AsyncSession, season: CareerSeason, bot_indexes: list[int], human_avg: float, config) -> list[dict]:
    rng = random.Random(season.id * 7919)
    offsets = config.career_difficulty_rating_offset or [-6, 0, 4]
    offset = offsets[DIFFICULTIES.index(season.difficulty)] if len(offsets) == 3 else 0
    spreads = [-4, -3, -1, 0, 1, 3, 4]
    rng.shuffle(spreads)
    names = rng.sample(BOT_CLUB_NAMES, len(bot_indexes))
    players = (await db.execute(
        select(Player).where(Player.is_active.is_(True)).order_by(Player.id).limit(2000)
    )).scalars().all()
    by_category: dict[str, list[Player]] = {cat: [p for p in players if p.position in pos] for cat, pos in CATEGORY_POSITIONS.items()}
    teams = []
    for n, index in enumerate(bot_indexes):
        formation = rng.choice(BOT_FORMATIONS)
        target = human_avg + offset + spreads[n % len(spreads)]
        used: set[int] = set()
        roster = []
        for slot in get_formation_slots(formation):
            candidates = [p for p in by_category[slot.category] if p.id not in used] or players
            ideal = [p for p in candidates if p.position == slot.ideal_position]
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
            "playstyle": rng.choice(PLAYSTYLES), "players": roster,
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
        cards = {c.id: c for c in await owned_cards(db, part.user_id)}
        xi = resolve_lineup(part, cards, 0, [])
        human_ratings.extend(_effective(c) for c, _ in xi)
        teams[part.team_index] = {"index": part.team_index, "name": _team_name(user), "user_id": part.user_id}
    human_avg = sum(human_ratings) / len(human_ratings) if human_ratings else 70
    bot_indexes = [i for i in range(TEAMS) if teams[i] is None]
    for bot in await _build_bots(db, season, bot_indexes, human_avg, config):
        teams[bot["index"]] = bot
    season.state = {"teams": teams, "fixtures": double_round_robin(), "schedule": build_schedule(now), "results": []}
    season.status = "active"
    season.starts_at = datetime.fromisoformat(season.state["schedule"][0])
    season.invite_expires_at = None


async def create_season(db: AsyncSession, user: User, difficulty: str, friend_id: Optional[int] = None) -> CareerSeason:
    config = await get_config(db)
    if not config.career_enabled:
        raise ConflictError("Карьера сейчас недоступна")
    if difficulty not in DIFFICULTIES:
        raise ConflictError("Неизвестная сложность")
    await wallet_service.lock_user_for_update(db, user.id)  # serializes "one season at a time"
    if await _current_participation(db, user.id):
        raise ConflictError("У тебя уже идёт сезон карьеры")
    squad = pick_squad(await owned_cards(db, user.id))

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
    season = CareerSeason(difficulty=difficulty, creator_id=user.id, status="pending", state={})
    season.participants.append(CareerParticipant(user_id=user.id, team_index=0, status="accepted", squad_card_ids=squad))
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
            f"({DIFFICULTY_LABELS[difficulty]}). Ответь в течение суток.",
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
        part.squad_card_ids = pick_squad(await owned_cards(db, user.id))
        part.status = "accepted"
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
    part.status = "left"
    await db.commit()


async def set_lineup(
    db: AsyncSession, user: User, slots: dict[str, int], formation: str, mentality: str, playstyle: str,
) -> None:
    part = await _current_participation(db, user.id)
    if part is None or part.status != "accepted":
        raise NotFoundError("Нет активного сезона")
    if formation not in CLUB_FORMATIONS:
        raise ConflictError("Неизвестная схема")
    if mentality not in MENTALITIES or playstyle not in PLAYSTYLES:
        raise ConflictError("Неизвестная тактика")
    slot_defs = {s.code: s for s in get_formation_slots(formation)}
    cards = {c.id: c for c in await owned_cards(db, user.id)}
    used_players: set[int] = set()
    clean: dict[str, int] = {}
    for code, card_id in slots.items():
        slot, card = slot_defs.get(code), cards.get(card_id)
        if slot is None or card is None or card_id not in part.squad_card_ids:
            raise ConflictError("В составе можно использовать только карточки заявки")
        if card.player.position not in CATEGORY_POSITIONS[slot.category] or card.player_id in used_players:
            raise ConflictError(f"{card.player.display_name} не подходит на позицию {code}")
        used_players.add(card.player_id)
        clean[code] = card_id
    part.formation, part.mentality, part.playstyle = formation, mentality, playstyle
    part.lineup = clean or None
    await db.commit()


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


async def _play_round(db: AsyncSession, season: CareerSeason, round_index: int, config) -> None:
    state = copy.deepcopy(season.state)
    teams = state["teams"]
    humans = {p.team_index: p for p in season.participants if p.status in ("accepted", "left")}
    cards_cache: dict[int, list[UserCard]] = {}
    played: dict[int, set[int]] = {}

    async def side_for(team_index: int):
        team = teams[team_index]
        if team.get("user_id") is None:
            return _bot_side(team, round_index, config)
        part = humans.get(team_index)
        if part is None or part.status != "accepted":
            return None  # left the season / declined: technical defeat
        if part.user_id not in cards_cache:
            cards_cache[part.user_id] = await owned_cards(db, part.user_id)
        cards = cards_cache[part.user_id]
        pairs = resolve_lineup(part, {c.id: c for c in cards}, round_index, [c for c in cards if _usable(c)])
        played[team_index] = {c.id for c, _ in pairs}
        return _human_side(part, pairs, config)

    results = []
    for home, away in state["fixtures"][round_index]:
        side_h, side_a = await side_for(home), await side_for(away)
        events = None
        if side_h and side_a:
            match = tournament_match_engine.simulate_match(
                side_h[0], side_a[0], side_h[1], side_a[1], config, teams[home]["name"], teams[away]["name"],
            )
            hs, as_ = match.score_a, match.score_b
            if teams[home].get("user_id") or teams[away].get("user_id"):
                events = match.event_log
        elif not side_h and not side_a:
            hs, as_ = 0, 0
        else:
            hs, as_ = (0, 3) if not side_h else (3, 0)
        results.append({"home": home, "away": away, "hs": hs, "as": as_, "events": events})
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
        names = {c.id: c.player.display_name for c in cards_cache.get(part.user_id, [])}
        report = _after_match(part, played.get(team_index, set()), own, opp, round_index, config, rng, names)
        reports[str(team_index)] = report
        flag_modified(part, "condition")

        reward = config.career_match_reward_win if own > opp else config.career_match_reward_draw if own == opp else 0
        part.coins_earned += await _credit(db, part.user_id, reward, f"Карьера: тур {round_index + 1}", season.id)
        outcome = "Победа" if own > opp else "Ничья" if own == opp else "Поражение"
        await notify(
            db, part.user_id, NotificationType.career_round_result, f"Карьера, тур {round_index + 1}: {outcome}",
            f"{own}:{opp} против «{opponent}»" + (f" · +{reward} монет" if reward else "") + _report_line(report),
            related_object_type="career_season", related_object_id=season.id,
        )

    season.state = state
    flag_modified(season, "state")
    season.rounds_played = round_index + 1
    if season.rounds_played >= ROUNDS:
        await _finish(db, season, config)


def _after_match(
    part: CareerParticipant, played_ids: set[int], own: int, opp: int, round_index: int, config,
    rng: random.Random, names: dict[int, str],
) -> dict:
    """Fatigue, injuries, yellow/red cards and form for one human squad after
    a round. Returns the round report (player names per event) shown in the
    calendar and the result notification."""
    report: dict[str, list[str]] = {"yellow": [], "red": [], "suspended": [], "injured": [], "form_up": [], "form_down": []}
    condition = dict(part.condition or {})
    for card_id in part.squad_card_ids:
        entry = {**_FRESH, **condition.get(str(card_id), {})}
        name = names.get(card_id, "Игрок")
        if card_id in played_ids:
            tired = entry["fatigue"] > 70
            entry["fatigue"] = min(100, entry["fatigue"] + config.career_fatigue_per_match)
            if rng.random() * 100 < config.career_injury_chance_pct * (2 if tired else 1):
                entry["injured_until"] = round_index + 1 + rng.randint(1, 2)
                report["injured"].append(name)
            # Discipline: a straight red, or the Nth yellow, = one round out.
            if rng.random() * 100 < config.career_red_chance_pct:
                entry["suspended_until"] = round_index + 2
                report["red"].append(name)
            elif rng.random() * 100 < config.career_yellow_chance_pct:
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
            entry["fatigue"] = max(0, entry["fatigue"] - config.career_fatigue_recovery)
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
    pct = (config.career_difficulty_reward_pct or [100, 150, 200])[DIFFICULTIES.index(season.difficulty)]
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
                message=f"Сезон карьеры ({DIFFICULTY_LABELS[season.difficulty]})",
            ))
        await notify(
            db, part.user_id, NotificationType.career_season_finished, f"Сезон карьеры завершён: {place} место",
            f"Награда: {coins} монет" + (" и трофей «Чемпион карьеры»" if place == 1 and trophy else ""),
            related_object_type="career_season", related_object_id=season.id,
        )
    season.status = "finished"
    season.finished_at = datetime.now(timezone.utc)


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
        at = _round_at(season, season.rounds_played)
        if at is None or at > now:
            break
        await _play_round(db, season, season.rounds_played, config)
        played += 1
    await db.commit()
    return played


REMINDER_WINDOW = timedelta(minutes=60)


async def send_reminders(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """"Скоро тур — проверь состав": one notification per human per round,
    for rounds starting within REMINDER_WINDOW. The bot calls this ~30 min
    before each slot; state["reminded"] keeps it to one per round."""
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
        reminded = list((season.state or {}).get("reminded") or [])
        if at is None or index in reminded or not (now < at <= now + REMINDER_WINDOW):
            await db.commit()
            continue
        teams = season.state["teams"]
        minutes = max(1, round((at - now).total_seconds() / 60))
        for part in season.participants:
            if part.status != "accepted":
                continue
            match = next(m for m in season.state["fixtures"][index] if part.team_index in m)
            opponent = teams[match[1] if match[0] == part.team_index else match[0]]["name"]
            await notify(
                db, part.user_id, NotificationType.career_reminder, f"Карьера: тур {index + 1} через {minutes} мин",
                f"Соперник — «{opponent}». Проверь состав: усталость, травмы и дисквалификации.",
                related_object_type="career_season", related_object_id=season.id,
            )
            sent += 1
        state = copy.deepcopy(season.state)
        state["reminded"] = reminded + [index]
        season.state = state
        flag_modified(season, "state")
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
    base = {"enabled": config.career_enabled, "difficulties": [
        {"code": d, "label": DIFFICULTY_LABELS[d], "reward_pct": (config.career_difficulty_reward_pct or [100, 150, 200])[i]}
        for i, d in enumerate(DIFFICULTIES)
    ], "place_rewards": config.career_place_rewards, "slots": [f"{h:02d}:{m:02d}" for h, m in CAREER_SLOTS],
        # The same slots as today's absolute times, so the client can show them
        # in the player's own time zone (the calendar does the same).
        "slot_times": _todays_slot_times()}
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
    }
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
    if me.status == "accepted":
        cards = await owned_cards(db, me.user_id)
        by_id = {c.id: c for c in cards}
        next_round = min(season.rounds_played, ROUNDS - 1)
        xi = resolve_lineup(me, by_id, next_round, [c for c in cards if _usable(c)])
        out["lineup"] = {slot.code: card.id for card, slot in xi}
        out["slots"] = [{"code": s.code, "category": s.category, "ideal_position": s.ideal_position.value}
                        for s in get_formation_slots(me.formation)]
        from app.schemas.card import UserCardOut

        for card_id in me.squad_card_ids:
            card = by_id.get(card_id)
            cond = _condition(me, card_id)
            out["squad"].append({
                "card": UserCardOut.model_validate(card) if card else None,
                "card_id": card_id,
                "fatigue": cond["fatigue"],
                "injured_rounds": max(0, cond["injured_until"] - next_round),
                "suspended_rounds": max(0, cond["suspended_until"] - next_round),
                "yellows": cond["yellows"],
                "form": cond["form"],
                "owned": card is not None,
            })
    return out


async def match_events(db: AsyncSession, user: User, season_id: int, round_index: int, match_index: int) -> dict:
    season = await db.get(CareerSeason, season_id)
    if season is None or not any(p.user_id == user.id for p in season.participants):
        raise NotFoundError("Матч не найден")
    results = (season.state or {}).get("results") or []
    if round_index >= len(results) or match_index >= len(results[round_index]):
        raise NotFoundError("Матч ещё не сыгран")
    m = results[round_index][match_index]
    teams = season.state["teams"]
    return {
        "home_name": teams[m["home"]]["name"], "away_name": teams[m["away"]]["name"],
        "home_score": m["hs"], "away_score": m["as"], "events": m.get("events") or [],
    }


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
