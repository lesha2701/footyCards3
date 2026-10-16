"""«Карьера игрока»: «Мой игрок» plays week-long league seasons for a club.

Clubs — the «Карьера тренера» club list, one league per division
(player_career_clubs): real clubs field their best cards, the rest are
generated. Signing needs rating AND prestige (MyPlayer.reputation, shown as
«Престиж»); the salary grows with the division, the club's stars and the
player's prestige.

Season — 8 clubs of the player's division (fillers when it's short),
double round-robin, 14 rounds at the «Карьера тренера» slots
(career_service.CAREER_SLOTS, so the bot's career scheduler resolves both).
The player starts for his club in his line; matches run on the
player-tournament engine and the player's goals / assists / match rating
come from the event log (shooter_id / assist_id). Coins per result and goal,
XP per match, place reward, salary and club objectives at the end. Every
match costs freshness (my_player_service); a tired player plays weaker.

Prestige — goals, assists, wins, titles, objectives, cups and the «Золотой
мяч» add it. Trophies: champion, league top scorer, player of the season.

Contract & transfer window — a contract runs config.player_career_contract_seasons
seasons. After every season clubs make offers (salary + signing bonus);
the player accepts or haggles (each counter-offer may make the club walk
away). When the contract has run out and no deal is signed, only the lower
divisions remain (free agent).

Cups and the «Золотой мяч» live in player_career_cups.

Every number comes from GameConfig.player_career_*.
"""
import copy
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
from app.models.player_career import PlayerCareerSeason
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services import my_player_service, player_career_clubs as pcc, player_career_cups as cups, tournament_match_engine, wallet_service
from app.services.career_service import ROUNDS, build_schedule, double_round_robin, standings
from app.services.player_career_clubs import club_access, club_catalog, find_club, market_salary, prestige_needed
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, on_ideal_position
from app.services.notification_service import notify
from app.services.player_tournament_simulation_service import _EngineCard, _engine_card

TEAMS = 8
FORMATION = "4-3-3"
MVP_AVG_RATING = 7.5
OBJECTIVE_AVG_RATING = 6.8
# Line -> (objective code, target) for the personal objective.
LINE_OBJECTIVE = {"FWD": ("goals", 8), "MID": ("goals", 4), "DEF": ("goals", 2), "GK": ("clean_sheets", 4)}
HAGGLE_STEPS = (10, 20, 30)
MAX_COUNTERS = 2


# --- clubs ----------------------------------------------------------------------------

def contract_expired(mp: MyPlayer) -> bool:
    return bool(mp.club_key) and (mp.contract_seasons_left or 0) <= 0


def _club_brief(club: dict, mp: MyPlayer, rating: int, config, free_agent: bool = False) -> dict:
    return {
        "key": club["key"], "name": club["name"], "rating": club["rating"], "is_demo": club["is_demo"],
        "real_cards": club["real_cards"], "league": club["league"], "level": club["level"],
        "club_stars": club["stars"], "reputation_needed": prestige_needed(club, config),
        "salary": market_salary(club, mp.reputation or 0, config),
        "locked_reason": club_access(club, rating, mp.reputation or 0, config, free_agent),
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


def _objective_label(code: str, target) -> str:
    return {
        "place": f"Финишировать не ниже {target} места",
        "goals": f"Забить {target} голов",
        "clean_sheets": f"Сыграть на ноль {target} матчей",
        "avg_rating": f"Средняя оценка {target}+",
    }[code]


def make_objectives(category: str, my_rank: int) -> list[dict]:
    """The club's objectives for a season: a place by the club's strength in
    the league, a personal target by the player's line, a match rating."""
    code, target = LINE_OBJECTIVE[category]
    return [
        {"code": "place", "target": min(TEAMS, my_rank + 1)},
        {"code": code, "target": target},
        {"code": "avg_rating", "target": OBJECTIVE_AVG_RATING},
    ]


def _objective_progress(objective: dict, state: dict, place: Optional[int]) -> tuple[float, bool]:
    """(current value, met so far) — the place only counts at the finish."""
    played = [v for v in (state.get("my_rounds") or {}).values() if v.get("played")]
    code, target = objective["code"], objective["target"]
    if code == "place":
        return (place or 0), place is not None and place <= target
    if code == "goals":
        value = sum(v["goals"] for v in played)
        return value, value >= target
    if code == "clean_sheets":
        value = sum(1 for v in played if v["opp"] == 0)
        return value, value >= target
    value = round(sum(v["rating"] for v in played) / len(played), 2) if played else 0
    return value, bool(played) and value >= target


def _objectives_out(season: PlayerCareerSeason, state: dict, table: list[dict]) -> list[dict]:
    current = next((n + 1 for n, row in enumerate(table) if row["team_index"] == 0), None)
    done_final = set(state.get("objectives_done") or [])
    out = []
    for objective in state.get("objectives") or []:
        value, met = _objective_progress(objective, state, current)
        out.append({
            "code": objective["code"], "target": objective["target"],
            "label": _objective_label(objective["code"], objective["target"]),
            "value": value, "met": objective["code"] in done_final if season.status != "active" else met,
        })
    return out


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
    table = standings(state) if teams else []
    return {
        "id": season.id, "status": season.status, "rounds_played": season.rounds_played, "total_rounds": ROUNDS,
        "next_round_at": schedule[season.rounds_played] if season.rounds_played < len(schedule) else None,
        "teams": [{"index": t["index"], "name": t["name"], "rating": t["rating"], "is_mine": t["index"] == 0} for t in teams],
        "table": table,
        "rounds": rounds,
        "stats": {
            "matches": len(my_rounds), "goals": sum(v["goals"] for v in my_rounds),
            "assists": sum(v["assists"] for v in my_rounds),
            "avg_rating": round(sum(v["rating"] for v in my_rounds) / len(my_rounds), 2) if my_rounds else None,
        },
        "scorers": scorers,
        "final_place": season.final_place, "coins_earned": season.coins_earned,
        "awards": state.get("awards") or [],
        "offers": [o for o in state.get("offers") or [] if "salary" in o],
        "league": state.get("league"),
        "objectives": _objectives_out(season, state, table),
        "salary": state.get("salary") or 0,
        "objective_coins": state.get("objective_coins") or 0,
    }


def _history_entry(season: PlayerCareerSeason) -> dict:
    state = season.state or {}
    played = [v for v in (state.get("my_rounds") or {}).values() if v.get("played")]
    teams = state.get("teams") or []
    return {
        "id": season.id, "club": teams[0]["name"] if teams else season.club_key,
        "club_rating": teams[0]["rating"] if teams else None,
        "place": season.final_place, "matches": len(played),
        "goals": sum(v["goals"] for v in played), "assists": sum(v["assists"] for v in played),
        "avg_rating": round(sum(v["rating"] for v in played) / len(played), 2) if played else None,
        "awards": state.get("awards") or [], "coins_earned": season.coins_earned,
        "finished_at": ensure_aware(season.finished_at).isoformat() if season.finished_at else None,
    }


async def history(db: AsyncSession, user_id: int, limit: int = 20) -> list[dict]:
    """Finished seasons, newest first — the career timeline."""
    rows = (await db.execute(
        select(PlayerCareerSeason).where(PlayerCareerSeason.user_id == user_id, PlayerCareerSeason.status == "finished")
        .order_by(PlayerCareerSeason.id.desc()).limit(limit)
    )).scalars().all()
    return [_history_entry(s) for s in rows]


async def get_view(db: AsyncSession, user: User) -> dict:
    config = await get_config(db)
    mp = await my_player_service.get_my_player(db, user.id)
    view: dict = {"enabled": config.player_career_enabled, "has_player": mp is not None}
    if mp is None:
        return view
    await pcc.prepare(db, config)
    season = await _active_season(db, user.id)
    if season is not None:
        await resolve_due(db, season.id)
        season = await db.get(PlayerCareerSeason, season.id)
    active_cup = await cups.active_cup(db, user.id)
    if active_cup is not None:
        await cups.resolve_cup(db, active_cup.id)
    await cups.award_golden_ball(db)
    if config.player_career_enabled:
        await cups.ensure_national(db, user.id, config)
    mp = await my_player_service.get_my_player(db, user.id)
    shown = season if season is not None and season.status == "active" else await _last_season(db, user.id)
    rating = my_player_service.rating_of(mp, config)
    clubs = await club_catalog(db, config)
    club = find_club(clubs, mp.club_key)
    if mp.club_key and (club is None or club["key"] != mp.club_key) and (season is None or season.status != "active"):
        # A key saved before the shared club list: keep the club under its new
        # key, or — when it's gone (the old demo ladder) — a free first pick.
        mp.club_key = club["key"] if club else None
        if club is None:
            mp.contract_salary, mp.contract_seasons_left = 0, 0
        await db.commit()
    expired = contract_expired(mp)
    view.update({
        "balance": (await db.get(User, user.id)).balance,
        "player": my_player_service.player_out(mp, config),
        "rating": rating,
        "reputation": mp.reputation or 0,
        "contract": {
            "salary": mp.contract_salary or (market_salary(club, mp.reputation or 0, config) if club else 0),
            "seasons_left": mp.contract_seasons_left or 0, "expired": expired,
            "free_agent_level": config.player_career_free_agent_level,
        } if mp.club_key else None,
        "national": cups.national_status(mp, config),
        "cups": await cups.cups_view(db, user.id),
        "golden_ball": await cups.golden_ball_view(db, user, config),
        "career": {"seasons": 0, "matches": 0, "goals": 0, "assists": 0, "titles": 0, "top_scorer": 0, "mvp": 0,
                   **(mp.career_stats or {})},
        "club": _club_brief(club, mp, rating, config) if club else None,
        "clubs": [_club_brief(c, mp, rating, config, free_agent=expired) for c in clubs],
        "season": _season_out(shown) if shown else None,
        # Picking a club freely: the first contract, or after the old one ran out.
        "can_change_club": (season is None or season.status != "active") and (not mp.club_key or expired),
        "haggle_steps": list(HAGGLE_STEPS), "max_counters": MAX_COUNTERS,
        "rewards": {
            "win": config.player_career_match_reward_win, "draw": config.player_career_match_reward_draw,
            "goal": config.player_career_goal_reward, "xp": config.player_career_match_xp,
            "places": list(config.player_career_place_rewards or []),
            "objective_coins": config.player_career_objective_coins,
            "objective_rep": config.player_career_objective_rep,
        },
        "history": await history(db, user.id),
        "freshness": {
            "value": my_player_service.freshness_now(mp, config, regen_bonus=await my_player_service.regen_bonus(db, user.id)),
            "per_match": config.my_player_freshness_per_match,
        },
    })
    return view


# --- contract & season lifecycle ---------------------------------------------------

def _require_enabled(config) -> None:
    if not config.player_career_enabled or not config.my_player_enabled:
        raise ConflictError("«Карьера игрока» сейчас недоступна")


def _sign(mp: MyPlayer, club: dict, salary: int, config) -> None:
    mp.club_key = club["key"]
    mp.contract_salary = salary
    mp.contract_seasons_left = max(1, config.player_career_contract_seasons)


async def sign_contract(db: AsyncSession, user: User, club_key: str) -> dict:
    """Picks a club from the list — the first contract, or after the old one
    ran out (then only the lower divisions). Otherwise clubs change through
    the transfer-window offers."""
    config = await get_config(db)
    _require_enabled(config)
    await pcc.prepare(db, config)
    await wallet_service.lock_user_for_update(db, user.id)  # serializes with season start
    mp = await _my_player(db, user)
    if await _active_season(db, user.id):
        raise ConflictError("Сменить клуб можно только между сезонами")
    clubs = await club_catalog(db, config)
    current = find_club(clubs, mp.club_key)
    if mp.club_key and current is None:
        mp.club_key = None  # the old club is gone: a free first pick
    expired = contract_expired(mp)
    if mp.club_key and not expired:
        raise ConflictError("Контракт ещё действует — перейти можно по предложению клуба в трансферное окно")
    club = find_club(clubs, club_key)
    if club is None:
        raise NotFoundError("Клуб не найден")
    reason = club_access(club, my_player_service.rating_of(mp, config), mp.reputation or 0, config, free_agent=expired)
    if reason:
        raise ConflictError(f"Клуб «{club['name']}» пока недоступен: {reason}")
    _sign(mp, club, market_salary(club, mp.reputation or 0, config), config)
    await db.commit()
    return await get_view(db, user)


def _team_from_club(index: int, club: dict) -> dict:
    rng = random.Random(pcc._seed(club["key"]))
    return {
        "index": index, "key": club["key"], "name": club["name"], "rating": club["rating"],
        "mentality": rng.choice(["BALANCED", "ATTACKING", "DEFENSIVE"]), "playstyle": rng.choice(["CENTRAL_PLAY", "WING_PLAY", "POSSESSION"]),
        "players": club["squad"],
    }


async def start_season(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    _require_enabled(config)
    now = now or datetime.now(timezone.utc)
    await pcc.prepare(db, config)
    await wallet_service.lock_user_for_update(db, user.id)
    mp = await _my_player(db, user)
    if not mp.club_key:
        raise ConflictError("Сначала подпиши контракт с клубом")
    if contract_expired(mp):
        raise ConflictError("Контракт закончился — прими предложение клуба или подпиши новый")
    if await _active_season(db, user.id):
        raise ConflictError("Сезон уже идёт")
    if await cups.active_cup(db, user.id, "cl"):
        raise ConflictError("Сначала доиграй Лигу чемпионов")
    clubs = await club_catalog(db, config)
    mine = find_club(clubs, mp.club_key)
    if mine is None:
        raise ConflictError("Твоего клуба больше нет в списке — выбери новый")
    mp.club_key = mine["key"]
    rivals = sorted(
        (c for c in clubs if c["key"] != mine["key"] and c["level"] == mine["level"]),
        key=lambda c: (abs(c["rating"] - mine["rating"]), c["key"]),
    )[:TEAMS - 1]
    if len(rivals) < TEAMS - 1:
        rivals += pcc.academy_fillers(mine, TEAMS - 1 - len(rivals), {c["name"] for c in clubs}, config)
    league = [mine, *rivals]
    teams = [_team_from_club(i, c) for i, c in enumerate(league)]
    my_rank = 1 + sum(1 for c in league[1:] if c["rating"] > mine["rating"])
    season = PlayerCareerSeason(
        user_id=user.id, club_key=mine["key"], status="active",
        state={"teams": teams, "fixtures": double_round_robin(TEAMS), "schedule": build_schedule(now),
               "results": [], "my_rounds": {}, "scorers": {}, "league": mine["league"],
               "objectives": make_objectives(my_player_service.category_of(mp.position), my_rank)},
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

def _side(team: dict, mine: Optional[SimpleNamespace], config, weaken_pct: int = 0):
    """Engine side for a club. `mine` (the user's engine card) replaces the
    weakest player of his line, at the slot closest to his position.
    `weaken_pct` lowers every rating (the opponent of a home match when «Мой
    игрок» wears an opp_home_pct «Артефакт»)."""
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
        rating = max(1, round(p["rating"] * (100 - weaken_pct) / 100)) if weaken_pct else p["rating"]
        player = SimpleNamespace(
            display_name=p["name"], position=Position(p["position"]), rating=rating, rarity=Rarity.common,
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


# Match rating by line: a clean sheet lifts keepers and defenders, every
# goal conceded beyond the first costs them — not only goals and assists count.
CLEAN_SHEET_BONUS = {"GK": 0.8, "DEF": 0.5, "MID": 0.2, "FWD": 0.0}
CONCEDED_PENALTY = {"GK": 0.25, "DEF": 0.1, "MID": 0.0, "FWD": 0.0}


def _match_rating(goals: int, assists: int, own: int, opp: int, rng: random.Random, line: str = "FWD") -> float:
    result = 0.5 if own > opp else 0.0 if own == opp else -0.4
    defence = CLEAN_SHEET_BONUS.get(line, 0) if opp == 0 else -CONCEDED_PENALTY.get(line, 0) * max(0, opp - 1)
    return round(max(4.0, min(10.0, 6.2 + goals * 1.0 + assists * 0.6 + result + defence + rng.uniform(-0.4, 0.5))), 1)


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
    from app.services import artifact_service

    home_edge = (await artifact_service.effects_of(db, season.user_id, "my_player", config)).get("opp_home_pct", 0) if mine else 0
    results = []
    my_match = None
    for home, away in state["fixtures"][round_index]:
        side_h = _side(teams[home], mine if home == 0 else None, config)
        side_a = _side(teams[away], mine if away == 0 else None, config, weaken_pct=home_edge if home == 0 else 0)
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
    line = my_player_service.category_of(mine.player.position) if mine is not None else "FWD"
    rating = _match_rating(goals, assists, own, opp, rng, line) if played else None
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
        my_player_service.add_xp(
            locked, config.player_career_match_xp, config,
            bonus_pct=await my_player_service.xp_bonus_pct(db, season.user_id),
        )
        mp.reputation = (mp.reputation or 0) + goals * config.player_career_rep_per_goal \
            + assists * config.player_career_rep_per_assist + (config.player_career_rep_per_win if own > opp else 0)
        stats = {**(mp.career_stats or {})}
        for k, v in (("matches", 1), ("goals", goals), ("assists", assists)):
            stats[k] = stats.get(k, 0) + v
        mp.career_stats = stats
        # Fatigue as of the round's own kick-off, so rounds resolved late in a
        # batch still get the recovery between them.
        schedule = state.get("schedule") or []
        at = ensure_aware(datetime.fromisoformat(schedule[round_index])) if round_index < len(schedule) else datetime.now(timezone.utc)
        if mp.freshness_at is not None and ensure_aware(mp.freshness_at) > at:
            at = ensure_aware(mp.freshness_at)
        fresh = my_player_service.freshness_now(mp, config, at, await my_player_service.regen_bonus(db, season.user_id))
        my_player_service.set_freshness(mp, fresh - config.my_player_freshness_per_match, at)
        await cups.record_match(db, season.user_id, at, goals, assists, rating, clean_sheet=opp == 0, line=line)
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

    # Contract: salary (if he played at all) and the club's objectives.
    clubs = await club_catalog(db, config)
    my_club = find_club(clubs, season.club_key)
    contract_salary = (mp.contract_salary if mp else 0) or (market_salary(my_club, mp.reputation or 0, config) if my_club and mp else 0)
    salary = contract_salary if my_rounds else 0
    season.coins_earned += await _credit(db, season.user_id, salary, f"Карьера игрока: зарплата за сезон в «{club}»", season.id)
    objectives_done = [o["code"] for o in state.get("objectives") or [] if _objective_progress(o, state, place)[1]]
    objective_coins = await _credit(
        db, season.user_id, len(objectives_done) * config.player_career_objective_coins,
        f"Карьера игрока: цели клуба ({len(objectives_done)})", season.id,
    )
    season.coins_earned += objective_coins

    offers: list[dict] = []
    if mp is not None:
        mp.reputation = (mp.reputation or 0) + len(objectives_done) * config.player_career_objective_rep
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
        if mp.club_key == season.club_key:
            mp.contract_seasons_left = max(0, (mp.contract_seasons_left or 0) - 1)
        offers = make_offers(clubs, my_club, mp, config, random.Random(season.id * 92821))
        league = state.get("league") or {}
        if my_club and league.get("level") == 1 and place <= config.player_career_cl_places:
            await cups.create_cl(db, season.user_id, season.id, my_club, config, datetime.now(timezone.utc))
    state = {
        **state, "awards": awards, "offers": offers,
        "salary": salary, "objectives_done": objectives_done, "objective_coins": objective_coins,
    }
    season.state = state
    flag_modified(season, "state")
    season.status = "finished"
    season.finished_at = datetime.now(timezone.utc)
    text = f"Награда: {coins} монет, зарплата: {salary}"
    if objectives_done:
        text += f" · цели клуба: {len(objectives_done)} из {len(state.get('objectives') or [])}"
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


# --- transfer window ------------------------------------------------------------------------

def _offer(club: dict, salary: int, bonus: int, renewal: bool) -> dict:
    return {
        "key": club["key"], "name": club["name"], "rating": club["rating"], "club_stars": club["stars"],
        "league": (club.get("league") or {}).get("name"), "level": club["level"],
        "salary": salary, "bonus": bonus, "counters": 0, "status": "open", "renewal": renewal,
    }


def make_offers(clubs: list[dict], current: Optional[dict], mp: MyPlayer, config, rng: random.Random) -> list[dict]:
    """End-of-season offers: stronger clubs the player can now sign for, and
    the current club's renewal once the contract has run out."""
    rating = my_player_service.rating_of(mp, config)
    prestige = mp.reputation or 0
    offers: list[dict] = []
    if current is not None and (mp.contract_seasons_left or 0) <= 0:
        salary = round(market_salary(current, prestige, config) * rng.uniform(0.95, 1.1) / 10) * 10
        offers.append(_offer(current, salary, round(salary * rng.uniform(0.1, 0.3) / 10) * 10, True))
    better = [
        c for c in clubs
        if (current is None or c["key"] != current["key"])
        and (current is None or (c["rating"], c["stars"], -c["level"]) > (current["rating"], current["stars"], -current["level"]))
        and club_access(c, rating, prestige, config) is None
    ]
    room = max(0, config.player_career_offers_max - len(offers))
    for club in rng.sample(better[: room * 3], min(room, len(better[: room * 3]))):
        salary = round(market_salary(club, prestige, config) * rng.uniform(0.9, 1.15) / 10) * 10
        offers.append(_offer(club, salary, round(salary * rng.uniform(0.3, 0.8) / 10) * 10, False))
    return offers


async def _window(db: AsyncSession, user: User) -> tuple[PlayerCareerSeason, MyPlayer, dict]:
    """The open transfer window: the latest season (finished) under its row
    lock, the player locked too."""
    await wallet_service.lock_user_for_update(db, user.id)
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    last = await _last_season(db, user.id)
    if last is None or last.status != "finished":
        raise ConflictError("Трансферное окно открыто только между сезонами")
    season = await _lock_season(db, last.id)
    return season, mp, copy.deepcopy(season.state)


def _find_offer(state: dict, key: str) -> dict:
    offer = next((o for o in state.get("offers") or [] if o.get("key") == key and "salary" in o), None)
    if offer is None:
        raise NotFoundError("Предложение не найдено")
    if offer["status"] != "open":
        raise ConflictError("Это предложение уже закрыто")
    return offer


async def accept_offer(db: AsyncSession, user: User, club_key: str) -> dict:
    """Signs the offer: new club (or renewal), agreed salary, signing bonus."""
    config = await get_config(db)
    _require_enabled(config)
    await pcc.prepare(db, config)
    season, mp, state = await _window(db, user)
    offer = _find_offer(state, club_key)
    club = find_club(await club_catalog(db, config), club_key)
    if club is None:
        raise ConflictError("Этого клуба больше нет — выбери другое предложение")
    _sign(mp, club, offer["salary"], config)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    if offer["bonus"] > 0:
        await wallet_service.credit_coins(
            db, locked, offer["bonus"], TransactionType.player_career_reward, f"Карьера игрока: бонус за подпись с «{club['name']}»",
            related_object_type="player_career_season", related_object_id=season.id,
        )
    for o in state.get("offers") or []:
        if o.get("status") == "open":
            o["status"] = "accepted" if o is offer else "closed"
    season.state = state
    flag_modified(season, "state")
    await db.commit()
    return await get_view(db, user)


async def counter_offer(db: AsyncSession, user: User, club_key: str, raise_pct: int, rng: Optional[random.Random] = None) -> dict:
    """Asks the club for raise_pct more salary and bonus. The club agrees with
    base - raise x raise_penalty - counters x repeat_penalty (+ a little for
    prestige) percent; otherwise it walks away for good."""
    config = await get_config(db)
    _require_enabled(config)
    if raise_pct not in HAGGLE_STEPS:
        raise ConflictError("Можно попросить +10, +20 или +30%")
    season, mp, state = await _window(db, user)
    offer = _find_offer(state, club_key)
    if offer["counters"] >= MAX_COUNTERS:
        raise ConflictError("Клуб больше не торгуется — прими или откажись")
    chance = (
        config.player_career_haggle_base - raise_pct * config.player_career_haggle_raise_penalty
        - offer["counters"] * config.player_career_haggle_repeat_penalty + min(15, (mp.reputation or 0) // 20)
    )
    chance = max(5, min(95, chance))
    agreed = (rng or random.Random()).random() * 100 < chance
    if agreed:
        offer["salary"] = round(offer["salary"] * (100 + raise_pct) / 100 / 10) * 10
        offer["bonus"] = round(offer["bonus"] * (100 + raise_pct) / 100 / 10) * 10
        offer["counters"] += 1
        offer["last"] = "agreed"
    else:
        offer["status"] = "withdrawn"
        offer["last"] = "walked"
    season.state = state
    flag_modified(season, "state")
    await db.commit()
    view = await get_view(db, user)
    view["haggle"] = {"club": offer["name"], "agreed": agreed, "chance": chance}
    return view


async def resolve_everything_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """League rounds, cup rounds, the monthly «Золотой мяч» (bot scheduler)."""
    return await resolve_all_due(db, now) + await cups.resolve_all_due(db, now)
