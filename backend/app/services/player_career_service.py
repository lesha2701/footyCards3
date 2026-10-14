"""«Карьера игрока»: «Мой игрок» plays a week-long league season for a club.

Stage 1 — clubs & contract. Clubs come from the cards themselves: every
`Player.club` with at least config.player_career_min_club_cards active
cards is a club whose squad is its best 4-3-3 XI (empty slots filled with
academy players a little below the club average); its rating is the XI
average. A ladder of demo clubs covers low ratings so a beginner always has
somewhere to start. A club is open when its rating <= player rating +
margin and the player's reputation is high enough for it.

Stage 2 — season. 8 clubs of similar strength (the player's club + the 7
closest), double round-robin, 14 rounds at the «Карьера тренера» slots
(career_service.CAREER_SLOTS, so the bot's career scheduler resolves both).
The player starts for his club in his line; matches run on the
player-tournament engine and the player's goals / assists / match rating
come from the event log (shooter_id / assist_id). Coins per result and goal,
XP per match, place reward at the end.

Stage 3 — reputation, transfers, awards. Goals, assists, wins and titles add
reputation; at the end of a season the clubs that became available (and are
stronger than the current one) are offered; the club can only be changed
between seasons. Trophies: champion, league top scorer, player of the season
(average rating 7.5+).

Every number comes from GameConfig.player_career_*.
"""
import copy
import hashlib
import random
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import NotificationType, Position, Rarity, TransactionType
from app.models.my_player import MyPlayer
from app.models.player import Player
from app.models.player_career import PlayerCareerSeason
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import my_player_service, tournament_match_engine, wallet_service
from app.services.career_service import ROUNDS, build_schedule, double_round_robin, standings
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, on_ideal_position
from app.services.notification_service import notify
from app.services.player_tournament_simulation_service import _EngineCard, _engine_card

TEAMS = 8
FORMATION = "4-3-3"
ACADEMY_GAP = 4
MVP_AVG_RATING = 7.5
DEMO_CLUBS = [
    ("Юность", 48), ("Заря", 52), ("Текстильщик", 55), ("Волна", 58), ("Сокол", 61),
    ("Металлург", 64), ("Энергия", 67), ("Нефтяник", 70), ("Олимп", 73), ("Авангард", 76),
]
_SURNAMES = [
    "Иванов", "Смирнов", "Кузнецов", "Попов", "Васильев", "Петров", "Соколов", "Михайлов", "Новиков", "Фёдоров",
    "Морозов", "Волков", "Алексеев", "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
    "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв", "Борисов", "Яковлев", "Григорьев",
]


# --- clubs catalog (stage 1) --------------------------------------------------------

def _seed(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def _academy(club: str, slot, rating: int, n: int) -> dict:
    rng = random.Random(_seed(f"{club}:{slot.code}:{n}"))
    return {
        "slot": slot.code, "player_id": 0, "name": f"{rng.choice('АБВГДЕКМНП')}. {rng.choice(_SURNAMES)}",
        "position": slot.ideal_position.value, "rating": max(40, min(99, rating)), "academy": True,
    }


def _club_squad(name: str, players: list[Player], fallback_rating: int) -> list[dict]:
    """Best XI for 4-3-3 from the club's cards, academy players in the gaps."""
    slots = get_formation_slots(FORMATION)
    pool = sorted(players, key=lambda p: (-p.rating, p.id))
    used: set[int] = set()
    squad: list[dict] = []
    for slot in sorted(slots, key=lambda s: 0 if s.category == "GK" else 1):
        fits = [p for p in pool if p.id not in used and p.position in CATEGORY_POSITIONS[slot.category]]
        ideal = [p for p in fits if on_ideal_position(p.position, slot.ideal_position)]
        pick = (ideal or fits or [None])[0]
        if pick is None:
            continue
        used.add(pick.id)
        squad.append({
            "slot": slot.code, "player_id": pick.id, "name": pick.display_name,
            "position": pick.position.value, "rating": pick.rating, "academy": False,
        })
    real_avg = round(sum(p["rating"] for p in squad) / len(squad)) if squad else fallback_rating
    taken = {p["slot"] for p in squad}
    for n, slot in enumerate(s for s in slots if s.code not in taken):
        squad.append(_academy(name, slot, real_avg - ACADEMY_GAP, n))
    order = {s.code: i for i, s in enumerate(slots)}
    return sorted(squad, key=lambda p: order[p["slot"]])


def _club_out(key: str, name: str, squad: list[dict], is_demo: bool, real_cards: int) -> dict:
    return {
        "key": key, "name": name, "is_demo": is_demo, "real_cards": real_cards,
        "rating": round(sum(p["rating"] for p in squad) / len(squad)), "squad": squad,
    }


async def club_catalog(db: AsyncSession, config) -> list[dict]:
    """Every club, strongest first. Computed from the cards on demand."""
    players = (await db.execute(select(Player).where(Player.is_active.is_(True)))).scalars().all()
    by_club: dict[str, list[Player]] = {}
    for p in players:
        if p.club:
            by_club.setdefault(p.club, []).append(p)
    clubs = [
        _club_out(f"club:{name}", name, _club_squad(name, members, 60), False, len(members))
        for name, members in by_club.items() if len(members) >= config.player_career_min_club_cards
    ]
    for name, rating in DEMO_CLUBS:
        slots = get_formation_slots(FORMATION)
        squad = [_academy(name, slot, rating + random.Random(_seed(name + slot.code)).randint(-2, 2), i) for i, slot in enumerate(slots)]
        clubs.append(_club_out(f"demo:{name}", name, squad, True, 0))
    return sorted(clubs, key=lambda c: (-c.get("rating", 0), c["name"]))


def reputation_needed(club_rating: int, config) -> int:
    return max(0, (club_rating - 60) * config.player_career_rep_per_club_rating)


def club_access(club: dict, player_rating: int, reputation: int, config) -> Optional[str]:
    """None when the player may sign for the club, else why not."""
    if club["rating"] > player_rating + config.player_career_rating_margin:
        return f"Нужен рейтинг {club['rating'] - config.player_career_rating_margin}+"
    need = reputation_needed(club["rating"], config)
    if reputation < need:
        return f"Нужна репутация {need}"
    return None


def _club_brief(club: dict, mp: MyPlayer, rating: int, config) -> dict:
    return {
        "key": club["key"], "name": club["name"], "rating": club["rating"], "is_demo": club["is_demo"],
        "real_cards": club["real_cards"], "reputation_needed": reputation_needed(club["rating"], config),
        "locked_reason": club_access(club, rating, mp.reputation or 0, config),
        "stars": [p["name"] for p in sorted(club["squad"], key=lambda p: -p["rating"]) if not p.get("academy")][:3],
    }


# --- read model ----------------------------------------------------------------

async def _my_player(db: AsyncSession, user: User) -> MyPlayer:
    mp = await my_player_service.get_my_player(db, user.id)
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    return mp


async def _active_season(db: AsyncSession, user_id: int) -> Optional[PlayerCareerSeason]:
    return (await db.execute(
        select(PlayerCareerSeason).where(PlayerCareerSeason.user_id == user_id, PlayerCareerSeason.status == "active")
    )).scalar_one_or_none()


async def _last_season(db: AsyncSession, user_id: int) -> Optional[PlayerCareerSeason]:
    return (await db.execute(
        select(PlayerCareerSeason).where(PlayerCareerSeason.user_id == user_id)
        .order_by(PlayerCareerSeason.id.desc()).limit(1)
    )).scalar_one_or_none()


def _season_out(season: PlayerCareerSeason) -> dict:
    state = season.state or {}
    schedule = state.get("schedule") or []
    results = state.get("results") or []
    teams = state.get("teams") or []
    rounds = []
    for r, fixtures in enumerate(state.get("fixtures") or []):
        played = results[r] if r < len(results) else None
        mine = next((m for m in (played or []) if 0 in (m["home"], m["away"])), None)
        fixture = next((f for f in fixtures if 0 in f), None)
        rounds.append({
            "index": r, "at": schedule[r] if r < len(schedule) else None,
            "home": fixture[0] if fixture else None, "away": fixture[1] if fixture else None,
            "hs": mine["hs"] if mine else None, "away_score": mine["as"] if mine else None,
            "me": (state.get("my_rounds") or {}).get(str(r)),
        })
    my_rounds = [v for v in (state.get("my_rounds") or {}).values() if v.get("played")]
    scorers = sorted((state.get("scorers") or {}).values(), key=lambda s: (-s["goals"], s["name"]))[:10]
    return {
        "id": season.id, "status": season.status, "rounds_played": season.rounds_played, "total_rounds": ROUNDS,
        "next_round_at": schedule[season.rounds_played] if season.rounds_played < len(schedule) else None,
        "teams": [{"index": t["index"], "name": t["name"], "rating": t["rating"], "is_mine": t["index"] == 0} for t in teams],
        "table": standings(state) if teams else [],
        "rounds": rounds,
        "stats": {
            "matches": len(my_rounds), "goals": sum(v["goals"] for v in my_rounds),
            "assists": sum(v["assists"] for v in my_rounds),
            "avg_rating": round(sum(v["rating"] for v in my_rounds) / len(my_rounds), 2) if my_rounds else None,
        },
        "scorers": scorers,
        "final_place": season.final_place, "coins_earned": season.coins_earned,
        "awards": state.get("awards") or [],
        "offers": state.get("offers") or [],
    }


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    mp = await my_player_service.get_my_player(db, user.id)
    view: dict = {"enabled": config.player_career_enabled, "has_player": mp is not None}
    if mp is None:
        return view
    season = await _active_season(db, user.id)
    if season is not None:
        await resolve_due(db, season.id)
        season = await db.get(PlayerCareerSeason, season.id)
    shown = season if season is not None and season.status == "active" else await _last_season(db, user.id)
    rating = my_player_service.rating_of(mp, config)
    clubs = await club_catalog(db, config)
    club = next((c for c in clubs if c["key"] == mp.club_key), None)
    view.update({
        "player": my_player_service.player_out(mp, config),
        "rating": rating,
        "reputation": mp.reputation or 0,
        "career": {"seasons": 0, "matches": 0, "goals": 0, "assists": 0, "titles": 0, "top_scorer": 0, "mvp": 0,
                   **(mp.career_stats or {})},
        "club": _club_brief(club, mp, rating, config) if club else None,
        "clubs": [_club_brief(c, mp, rating, config) for c in clubs],
        "season": _season_out(shown) if shown else None,
        "can_change_club": season is None or season.status != "active",
        "rewards": {
            "win": config.player_career_match_reward_win, "draw": config.player_career_match_reward_draw,
            "goal": config.player_career_goal_reward, "xp": config.player_career_match_xp,
            "places": list(config.player_career_place_rewards or []),
        },
    })
    return view


# --- contract & season lifecycle ---------------------------------------------------

def _require_enabled(config) -> None:
    if not config.player_career_enabled or not config.my_player_enabled:
        raise ConflictError("«Карьера игрока» сейчас недоступна")


async def sign_contract(db: AsyncSession, user: User, club_key: str) -> dict:
    """Signs for a club — only between seasons, only an open club."""
    config = await get_config(db)
    _require_enabled(config)
    await wallet_service.lock_user_for_update(db, user.id)  # serializes with season start
    mp = await _my_player(db, user)
    if await _active_season(db, user.id):
        raise ConflictError("Сменить клуб можно только между сезонами")
    clubs = {c["key"]: c for c in await club_catalog(db, config)}
    club = clubs.get(club_key)
    if club is None:
        raise NotFoundError("Клуб не найден")
    reason = club_access(club, my_player_service.rating_of(mp, config), mp.reputation or 0, config)
    if reason:
        raise ConflictError(f"Клуб «{club['name']}» пока недоступен: {reason}")
    mp.club_key = club_key
    await db.commit()
    return await get_view(db, user)


def _team_from_club(index: int, club: dict) -> dict:
    rng = random.Random(_seed(club["key"]))
    return {
        "index": index, "key": club["key"], "name": club["name"], "rating": club["rating"],
        "mentality": rng.choice(["BALANCED", "ATTACKING", "DEFENSIVE"]), "playstyle": rng.choice(["CENTRAL_PLAY", "WING_PLAY", "POSSESSION"]),
        "players": club["squad"],
    }


async def start_season(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    now = now or datetime.now(timezone.utc)
    await wallet_service.lock_user_for_update(db, user.id)
    mp = await _my_player(db, user)
    if not mp.club_key:
        raise ConflictError("Сначала подпиши контракт с клубом")
    if await _active_season(db, user.id):
        raise ConflictError("Сезон уже идёт")
    clubs = await club_catalog(db, config)
    mine = next((c for c in clubs if c["key"] == mp.club_key), None)
    if mine is None:
        raise ConflictError("Твоего клуба больше нет в каталоге — выбери новый")
    rivals = sorted((c for c in clubs if c["key"] != mine["key"]), key=lambda c: (abs(c["rating"] - mine["rating"]), c["key"]))
    league = [mine, *rivals[:TEAMS - 1]]
    teams = [_team_from_club(i, c) for i, c in enumerate(league)]
    season = PlayerCareerSeason(
        user_id=user.id, club_key=mine["key"], status="active",
        state={"teams": teams, "fixtures": double_round_robin(TEAMS), "schedule": build_schedule(now),
               "results": [], "my_rounds": {}, "scorers": {}},
    )
    db.add(season)
    await db.commit()
    return await get_view(db, user)


async def leave_season(db: AsyncSession, user: User) -> dict:
    season = await _active_season(db, user.id)
    if season is None:
        raise NotFoundError("Нет активного сезона")
    season = await _lock_season(db, season.id)
    season.status = "cancelled"
    season.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_view(db, user)


async def _lock_season(db: AsyncSession, season_id: int) -> PlayerCareerSeason:
    season = (await db.execute(
        select(PlayerCareerSeason).where(PlayerCareerSeason.id == season_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if season is None:
        raise NotFoundError("Сезон не найден")
    return season


# --- playing rounds (stage 2) ---------------------------------------------------------

def _side(team: dict, mine: Optional[SimpleNamespace], config):
    """Engine side for a club. `mine` (the user's engine card) replaces the
    weakest player of his line, at the slot closest to his position."""
    slots = {s.code: s for s in get_formation_slots(FORMATION)}
    roster = list(team["players"])
    my_slot = None
    if mine is not None:
        category = next(cat for cat, pos in CATEGORY_POSITIONS.items() if mine.player.position in pos)
        line = [p for p in roster if slots[p["slot"]].category == category]
        exact = [p for p in line if on_ideal_position(mine.player.position, slots[p["slot"]].ideal_position)]
        replaced = min(exact or line, key=lambda p: p["rating"])
        my_slot = replaced["slot"]
    with_slots = []
    for i, p in enumerate(roster):
        slot = slots[p["slot"]]
        if p["slot"] == my_slot:
            with_slots.append((_engine_card(mine, config), slot))
            continue
        player = SimpleNamespace(
            display_name=p["name"], position=Position(p["position"]), rating=p["rating"], rarity=Rarity.common,
            club=team["name"], country="", attack_rating=None, defense_rating=None,
        )
        with_slots.append((_EngineCard(id=-(team["index"] * 100 + i + 1), player_id=p.get("player_id") or 0, player=player), slot))
    side = build_side(with_slots, team["mentality"], team["playstyle"])
    lineup = [
        {"club_card_id": c.id, "player_id": c.player_id, "name": c.player.display_name, "rating": c.player.rating,
         "position": c.player.position.value, "category": slot.category, **({"skill": c.skill} if c.skill else {})}
        for c, slot in with_slots
    ]
    return side, lineup


def _match_rating(goals: int, assists: int, own: int, opp: int, rng: random.Random) -> float:
    result = 0.5 if own > opp else 0.0 if own == opp else -0.4
    return round(max(4.0, min(10.0, 6.2 + goals * 1.0 + assists * 0.6 + result + rng.uniform(-0.4, 0.5))), 1)


async def _credit(db: AsyncSession, user_id: int, amount: int, description: str, season_id: int) -> int:
    if amount <= 0:
        return 0
    locked = await wallet_service.lock_user_for_update(db, user_id)
    await wallet_service.credit_coins(
        db, locked, amount, TransactionType.player_career_reward, description,
        related_object_type="player_career_season", related_object_id=season_id,
    )
    return amount


async def _play_round(db: AsyncSession, season: PlayerCareerSeason, round_index: int, config) -> None:
    state = copy.deepcopy(season.state)
    teams = state["teams"]
    mine = await my_player_service.engine_card(db, season.user_id, config)
    my_id = mine.id if mine is not None else None
    results = []
    my_match = None
    for home, away in state["fixtures"][round_index]:
        side_h = _side(teams[home], mine if home == 0 else None, config)
        side_a = _side(teams[away], mine if away == 0 else None, config)
        match = tournament_match_engine.simulate_match(
            side_h[0], side_a[0], side_h[1], side_a[1], config, teams[home]["name"], teams[away]["name"],
        )
        for event in match.event_log:
            if event.get("event_type") != "goal":
                continue
            payload = event.get("payload") or {}
            team = teams[home] if event.get("team") == "a" else teams[away]
            if payload.get("shooter"):
                key = f"{team['index']}:{payload['shooter']}"
                row = state["scorers"].setdefault(key, {"name": payload["shooter"], "team": team["name"], "goals": 0})
                row["goals"] += 1
        entry = {"home": home, "away": away, "hs": match.score_a, "as": match.score_b}
        if 0 in (home, away):
            my_match = (entry, match.event_log, "a" if home == 0 else "b")
        results.append(entry)
    state["results"].append(results)

    entry, events, my_side = my_match
    own, opp = (entry["hs"], entry["as"]) if my_side == "a" else (entry["as"], entry["hs"])
    goals = sum(1 for e in events if e.get("event_type") == "goal" and e.get("team") == my_side
                and (e.get("payload") or {}).get("shooter_id") == my_id and my_id is not None)
    assists = sum(1 for e in events if e.get("event_type") == "goal" and e.get("team") == my_side
                  and (e.get("payload") or {}).get("assist_id") == my_id and my_id is not None)
    played = mine is not None
    rng = random.Random(season.id * 31337 + round_index)
    rating = _match_rating(goals, assists, own, opp, rng) if played else None
    opponent = teams[entry["away"] if my_side == "a" else entry["home"]]["name"]
    state["my_rounds"][str(round_index)] = {
        "played": played, "goals": goals, "assists": assists, "rating": rating, "own": own, "opp": opp,
        "opponent": opponent,
    }

    reward = config.player_career_match_reward_win if own > opp else config.player_career_match_reward_draw if own == opp else 0
    reward += goals * config.player_career_goal_reward
    season.coins_earned += await _credit(db, season.user_id, reward, f"Карьера игрока: тур {round_index + 1}", season.id)
    mp = (await db.execute(select(MyPlayer).where(MyPlayer.user_id == season.user_id).with_for_update())).scalar_one_or_none()
    if mp is not None and played:
        locked = await wallet_service.lock_user_for_update(db, season.user_id)
        my_player_service.add_xp(locked, config.player_career_match_xp, config)
        mp.reputation = (mp.reputation or 0) + goals * config.player_career_rep_per_goal \
            + assists * config.player_career_rep_per_assist + (config.player_career_rep_per_win if own > opp else 0)
        stats = {**(mp.career_stats or {})}
        for k, v in (("matches", 1), ("goals", goals), ("assists", assists)):
            stats[k] = stats.get(k, 0) + v
        mp.career_stats = stats
    outcome = "Победа" if own > opp else "Ничья" if own == opp else "Поражение"
    personal = f" · голы: {goals}" if goals else ""
    personal += f" · передачи: {assists}" if assists else ""
    personal += f" · оценка {rating}" if rating is not None else ""
    await notify(
        db, season.user_id, NotificationType.player_career_round_result, f"Карьера игрока, тур {round_index + 1}: {outcome}",
        f"{own}:{opp} против «{opponent}»{personal}" + (f" · +{reward} монет" if reward else ""),
        related_object_type="player_career_season", related_object_id=season.id,
    )
    season.state = state
    flag_modified(season, "state")
    season.rounds_played = round_index + 1
    if season.rounds_played >= ROUNDS:
        await _finish(db, season, config)


async def _grant_trophy(db: AsyncSession, user_id: int, code: str, message: str) -> Optional[str]:
    trophy = (await db.execute(
        select(TrophyDefinition).where(TrophyDefinition.code == code, TrophyDefinition.is_active.is_(True))
    )).scalar_one_or_none()
    if trophy is None:
        return None
    db.add(UserTrophy(user_id=user_id, trophy_definition_id=trophy.id, message=message))
    return trophy.name


async def _finish(db: AsyncSession, season: PlayerCareerSeason, config) -> None:
    """Place reward, awards (stage 3), reputation and the transfer offers."""
    state = season.state
    table = standings(state)
    place = next(n + 1 for n, row in enumerate(table) if row["team_index"] == 0)
    season.final_place = place
    rewards = config.player_career_place_rewards or []
    coins = await _credit(
        db, season.user_id, int(rewards[place - 1]) if place - 1 < len(rewards) else 0,
        f"Карьера игрока: {place} место", season.id,
    )
    season.coins_earned += coins

    my_rounds = [v for v in state["my_rounds"].values() if v.get("played")]
    my_goals = sum(v["goals"] for v in my_rounds)
    avg = sum(v["rating"] for v in my_rounds) / len(my_rounds) if my_rounds else 0
    club = state["teams"][0]["name"]
    awards: list[str] = []
    mp = (await db.execute(select(MyPlayer).where(MyPlayer.user_id == season.user_id).with_for_update())).scalar_one_or_none()
    others = [s["goals"] for k, s in state["scorers"].items() if not (mp and k == f"0:{mp.name}")]
    if place == 1 and (name := await _grant_trophy(db, season.user_id, "player_career_champion", f"Сезон за «{club}»")):
        awards.append(name)
    if my_goals > 0 and my_goals >= max(others, default=0) and (
        name := await _grant_trophy(db, season.user_id, "player_career_top_scorer", f"{my_goals} голов за «{club}»")
    ):
        awards.append(name)
    if avg >= MVP_AVG_RATING and (name := await _grant_trophy(db, season.user_id, "player_career_mvp", f"Средняя оценка {avg:.2f}")):
        awards.append(name)

    offers: list[dict] = []
    if mp is not None:
        stats = {**(mp.career_stats or {})}
        stats["seasons"] = stats.get("seasons", 0) + 1
        if place == 1:
            stats["titles"] = stats.get("titles", 0) + 1
            mp.reputation = (mp.reputation or 0) + config.player_career_rep_title
        if "Лучший бомбардир" in awards:
            stats["top_scorer"] = stats.get("top_scorer", 0) + 1
        if "Игрок сезона" in awards:
            stats["mvp"] = stats.get("mvp", 0) + 1
        mp.career_stats = stats
        rating = my_player_service.rating_of(mp, config)
        current = state["teams"][0]["rating"]
        offers = [
            {"key": c["key"], "name": c["name"], "rating": c["rating"]}
            for c in await club_catalog(db, config)
            if c["key"] != season.club_key and c["rating"] > current
            and club_access(c, rating, mp.reputation or 0, config) is None
        ][:3]
    state = {**state, "awards": awards, "offers": offers}
    season.state = state
    flag_modified(season, "state")
    season.status = "finished"
    season.finished_at = datetime.now(timezone.utc)
    text = f"Награда: {coins} монет"
    if awards:
        text += " · трофеи: " + ", ".join(awards)
    if offers:
        text += " · есть предложения от клубов!"
    await notify(
        db, season.user_id, NotificationType.player_career_season_finished,
        f"Сезон за «{club}» завершён: {place} место", text,
        related_object_type="player_career_season", related_object_id=season.id,
    )


async def resolve_due(db: AsyncSession, season_id: int, now: Optional[datetime] = None) -> int:
    """Plays every round whose time has come; the season row lock keeps a
    round from ever being played twice. Returns rounds played."""
    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    season = await _lock_season(db, season_id)
    played = 0
    schedule = (season.state or {}).get("schedule") or []
    while season.status == "active" and season.rounds_played < ROUNDS:
        at = ensure_aware(datetime.fromisoformat(schedule[season.rounds_played])) if season.rounds_played < len(schedule) else None
        if at is None or at > now:
            break
        await _play_round(db, season, season.rounds_played, config)
        played += 1
    await db.commit()
    return played


async def resolve_all_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    ids = (await db.execute(select(PlayerCareerSeason.id).where(PlayerCareerSeason.status == "active"))).scalars().all()
    return sum([await resolve_due(db, season_id, now) for season_id in ids])
