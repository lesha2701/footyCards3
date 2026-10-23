"""«Карьера игрока» beyond the league: cups and the «Золотой мяч».

- Лига чемпионов (kind "cl"): the top config.player_career_cl_places of a
  division-1 season qualify; 8 clubs (the best of division 1), knockout —
  1/4, 1/2, final — at the next three career slots. Created at the end of
  the league season; the next season waits until it's over.
- Турнир сборных (kind "national"): every two weeks a player with a chosen
  country and prestige >= config.player_career_national_prestige is called
  up; 8 national teams built from the cards of each country, same knockout.
- Coins for every round won (config *_rewards), XP per match, prestige and a
  trophy for the title; the player's match stats feed the month table.
- «Золотой мяч»: the best of the month by score = average rating x 10 +
  goals, assists and clean sheets weighted by the player's line (LINE_WEIGHTS:
  a defender's goal is worth more than a forward's, keepers and defenders
  score with clean sheets), at least config min matches. Awarded once per
  month (PlayerCareerGoldenBall's primary key) when the next month starts.
"""
import copy
import random
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.enums import NotificationType, TransactionType
from app.models.my_player import MyPlayer
from app.models.player import Player
from app.models.player_career import PlayerCareerCup, PlayerCareerGoldenBall, PlayerCareerMonthStat
from app.models.user import User
from app.services import my_player_service, player_career_clubs as pcc, tournament_match_engine, wallet_service
from app.services.career_service import build_schedule
from app.services.notification_service import notify

CUP_TEAMS = 8
CUP_ROUNDS = 3
ROUND_LABELS = ("1/4 финала", "1/2 финала", "Финал")
CUP_TITLES = {"cl": "Лига чемпионов", "national": "Турнир сборных"}
CUP_TROPHIES = {"cl": "player_career_cl_winner", "national": "player_career_national_winner"}
GOLDEN_BALL_TROPHY = "player_career_golden_ball"
# Two-week windows of the national tournament count from this Monday.
NATIONAL_EPOCH = date(2026, 1, 5)
DEFAULT_COUNTRIES = [
    "Россия", "Бразилия", "Аргентина", "Франция", "Германия", "Испания", "Англия", "Италия", "Португалия",
    "Нидерланды", "Бельгия", "Хорватия", "Уругвай", "Колумбия", "Мексика", "США", "Япония", "Корея", "Марокко",
    "Сенегал", "Нигерия", "Египет", "Польша", "Сербия", "Турция", "Украина", "Беларусь", "Казахстан", "Швеция",
    "Норвегия", "Дания", "Швейцария", "Австрия", "Чехия", "Шотландия", "Уэльс",
]
# Points per goal / assist / clean sheet by line — every line can win.
LINE_WEIGHTS = {
    "FWD": {"goals": 3, "assists": 2, "clean_sheets": 0},
    "MID": {"goals": 4, "assists": 3, "clean_sheets": 1},
    "DEF": {"goals": 6, "assists": 3, "clean_sheets": 4},
    "GK": {"goals": 6, "assists": 3, "clean_sheets": 7},
}
MONTHS = ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь")


def month_key(at: datetime) -> str:
    local = ensure_aware(at).astimezone(app_timezone())
    return f"{local.year:04d}-{local.month:02d}"


def month_label(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTHS[int(month) - 1].capitalize()} {year}"


def national_window(today: date) -> str:
    return f"w{(today - NATIONAL_EPOCH).days // 14}"


async def countries(db: AsyncSession) -> list[str]:
    """Countries a player can represent: the cards' countries plus a default list."""
    on_cards = (await db.execute(select(Player.country).where(Player.is_active.is_(True)).distinct())).scalars().all()
    return sorted({c.strip() for c in [*on_cards, *DEFAULT_COUNTRIES] if c and c.strip()})


# --- month stats & «Золотой мяч» --------------------------------------------------------

async def record_match(
    db: AsyncSession, user_id: int, at: datetime, goals: int, assists: int, rating: float,
    clean_sheet: bool = False, line: str = "FWD",
) -> None:
    """Adds one played match to the player's month line (the line is the
    player's current one). Caller holds the user lock."""
    key = month_key(at)
    row = (await db.execute(
        select(PlayerCareerMonthStat).where(PlayerCareerMonthStat.user_id == user_id, PlayerCareerMonthStat.month == key)
    )).scalar_one_or_none()
    if row is None:
        row = PlayerCareerMonthStat(user_id=user_id, month=key, matches=0, goals=0, assists=0, rating_sum=0, clean_sheets=0)
        db.add(row)
    row.matches += 1
    row.goals += goals
    row.assists += assists
    row.clean_sheets = (row.clean_sheets or 0) + int(clean_sheet)
    row.rating_sum += float(rating)
    row.line = line
    from app.services.player_career_life import record_week

    await record_week(db, user_id, at, goals, assists, rating, clean_sheet)


def score_of(row: PlayerCareerMonthStat) -> float:
    avg = row.rating_sum / row.matches if row.matches else 0
    w = LINE_WEIGHTS.get(row.line or "FWD", LINE_WEIGHTS["FWD"])
    return round(avg * 10 + row.goals * w["goals"] + row.assists * w["assists"] + (row.clean_sheets or 0) * w["clean_sheets"], 1)


async def _month_table(db: AsyncSession, key: str, config, limit: int = 20) -> list[tuple[PlayerCareerMonthStat, User]]:
    rows = (await db.execute(
        select(PlayerCareerMonthStat, User).join(User, User.id == PlayerCareerMonthStat.user_id)
        .where(PlayerCareerMonthStat.month == key)
    )).all()
    eligible = [(r, u) for r, u in rows if r.matches >= config.player_career_golden_ball_min_matches]
    return sorted(eligible, key=lambda ru: (-score_of(ru[0]), ru[0].user_id))[:limit]


async def award_golden_ball(db: AsyncSession, now: Optional[datetime] = None) -> Optional[int]:
    """Awards last month's «Золотой мяч» once (a row is written even with no
    winner). Returns the winner's user id. Commits."""
    from app.services.game_config_service import get_config
    from app.services.player_career_service import _grant_trophy

    now = now or datetime.now(timezone.utc)
    local = ensure_aware(now).astimezone(app_timezone())
    first = local.replace(day=1)
    previous = month_key(first - timedelta(days=1))
    if await db.get(PlayerCareerGoldenBall, previous):
        return None
    config = await get_config(db)
    table = await _month_table(db, previous, config, limit=1)
    winner = table[0] if table else None
    row = PlayerCareerGoldenBall(month=previous, user_id=None, score=0)
    if winner:
        stat, user = winner
        row.user_id = user.id
        row.score = score_of(stat)
        row.goals, row.assists = stat.goals, stat.assists
        row.avg_rating = round(stat.rating_sum / stat.matches, 2)
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        return None  # someone else just awarded it
    if winner:
        stat, user = winner
        await _grant_trophy(db, user.id, GOLDEN_BALL_TROPHY, f"{month_label(previous)}: {stat.goals} голов, оценка {row.avg_rating}")
        locked = await wallet_service.lock_user_for_update(db, user.id)
        if config.player_career_golden_ball_coins > 0:
            await wallet_service.credit_coins(
                db, locked, config.player_career_golden_ball_coins, TransactionType.player_career_reward,
                f"Золотой мяч · {month_label(previous)}", related_object_type="player_career_golden_ball",
            )
        mp = await my_player_service.get_my_player(db, user.id)
        if mp is not None:
            mp.reputation = (mp.reputation or 0) + config.player_career_golden_ball_prestige
        await notify(
            db, user.id, NotificationType.player_career_event, "🏆 Ты выиграл «Золотой мяч»!",
            f"Лучший игрок за {month_label(previous).lower()}: +{config.player_career_golden_ball_coins} монет и "
            f"+{config.player_career_golden_ball_prestige} престижа",
        )
    await db.commit()
    return winner[1].id if winner else None


async def golden_ball_view(db: AsyncSession, user: User, config, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    key = month_key(now)
    table = await _month_table(db, key, config)
    mine = (await db.execute(
        select(PlayerCareerMonthStat).where(PlayerCareerMonthStat.user_id == user.id, PlayerCareerMonthStat.month == key)
    )).scalar_one_or_none()
    my_place = None
    if mine is not None and mine.matches >= config.player_career_golden_ball_min_matches:
        ahead = (await db.execute(
            select(func.count()).select_from(PlayerCareerMonthStat).where(
                PlayerCareerMonthStat.month == key,
                PlayerCareerMonthStat.matches >= config.player_career_golden_ball_min_matches,
            )
        )).scalar_one()
        all_rows = await _month_table(db, key, config, limit=max(1, ahead))
        my_place = next((i + 1 for i, (r, _) in enumerate(all_rows) if r.user_id == user.id), None)
    winners = (await db.execute(
        select(PlayerCareerGoldenBall, User).outerjoin(User, User.id == PlayerCareerGoldenBall.user_id)
        .where(PlayerCareerGoldenBall.user_id.is_not(None)).order_by(PlayerCareerGoldenBall.month.desc()).limit(6)
    )).all()

    def entry(stat: PlayerCareerMonthStat, owner: User, place: int) -> dict:
        return {
            "place": place, "user_id": owner.id, "user_name": owner.first_name or owner.username or "Игрок",
            "is_me": owner.id == user.id, "matches": stat.matches, "goals": stat.goals, "assists": stat.assists,
            "clean_sheets": stat.clean_sheets or 0, "line": stat.line or "FWD",
            "avg_rating": round(stat.rating_sum / stat.matches, 2) if stat.matches else None, "score": score_of(stat),
        }

    return {
        "month": key, "month_label": month_label(key), "min_matches": config.player_career_golden_ball_min_matches,
        "prize_coins": config.player_career_golden_ball_coins, "prize_prestige": config.player_career_golden_ball_prestige,
        "weights": LINE_WEIGHTS,
        "table": [entry(r, u, i + 1) for i, (r, u) in enumerate(table)],
        "me": entry(mine, user, my_place or 0) if mine is not None else None,
        "winners": [
            {"month": g.month, "month_label": month_label(g.month), "user_name": (u.first_name or u.username or "Игрок") if u else "—",
             "is_me": bool(u and u.id == user.id), "score": g.score, "goals": g.goals, "avg_rating": g.avg_rating}
            for g, u in winners
        ],
    }


# --- cups ------------------------------------------------------------------------------------

def _team(index: int, club: dict) -> dict:
    rng = random.Random(pcc._seed(club["key"]))
    return {
        "index": index, "key": club["key"], "name": club["name"], "rating": club["rating"],
        "mentality": rng.choice(["BALANCED", "ATTACKING", "DEFENSIVE"]), "playstyle": rng.choice(["CENTRAL_PLAY", "WING_PLAY", "POSSESSION"]),
        "players": club["squad"],
    }


def _bracket(teams: list[dict]) -> list[list[int]]:
    """Quarter-finals seeded by rating: 1v8, 4v5, 2v7, 3v6."""
    order = [t["index"] for t in sorted(teams, key=lambda t: -t["rating"])]
    return [[order[0], order[7]], [order[3], order[4]], [order[1], order[6]], [order[2], order[5]]]


def _new_state(kind: str, title: str, teams: list[dict], now: datetime) -> dict:
    return {
        "kind": kind, "title": title, "teams": teams, "schedule": build_schedule(now)[:CUP_ROUNDS],
        "pairs": [_bracket(teams)], "results": [], "my_rounds": {}, "alive": True, "won": False,
    }


async def active_cup(db: AsyncSession, user_id: int, kind: Optional[str] = None) -> Optional[PlayerCareerCup]:
    query = select(PlayerCareerCup).where(PlayerCareerCup.user_id == user_id, PlayerCareerCup.status == "active")
    if kind:
        query = query.where(PlayerCareerCup.kind == kind)
    return (await db.execute(query.order_by(PlayerCareerCup.id.desc()).limit(1))).scalar_one_or_none()


async def create_cl(db: AsyncSession, user_id: int, season_id: int, my_club: dict, config, now: datetime) -> Optional[PlayerCareerCup]:
    """Champions League after a top-division season (caller checked the place)."""
    clubs = await pcc.club_catalog(db, config)
    others = [c for c in clubs if c["level"] == 1 and c["key"] != my_club["key"]][: CUP_TEAMS - 1]
    if len(others) < CUP_TEAMS - 1:
        base = pcc.pick(config.player_career_level_ratings, 0, 80)
        names = {c["name"] for c in clubs}
        extra = [c for c in clubs if c["level"] != 1 and c["key"] != my_club["key"] and c not in others]
        others += extra[: CUP_TEAMS - 1 - len(others)]
        while len(others) < CUP_TEAMS - 1:
            name = f"Европа {len(others) + 1}"
            squad = pcc.academy_squad(f"cl:{name}", base)
            if name not in names:
                others.append({"key": f"gen:{name}", "name": name, "rating": pcc.avg_rating(squad), "squad": squad})
    teams = [_team(i, c) for i, c in enumerate([my_club, *others])]
    cup = PlayerCareerCup(
        user_id=user_id, kind="cl", window_key=f"season:{season_id}", status="active",
        state=_new_state("cl", CUP_TITLES["cl"], teams, now),
    )
    db.add(cup)
    await db.flush()
    await notify(
        db, user_id, NotificationType.player_career_event, "Ты в Лиге чемпионов! ⭐",
        f"«{my_club['name']}» сыграет в Лиге чемпионов: 1/4 финала уже скоро",
        related_object_type="player_career_cup", related_object_id=cup.id,
    )
    return cup


async def _nation_teams(db: AsyncSession, country: str, config) -> list[dict]:
    players = (await db.execute(select(Player).where(Player.is_active.is_(True)))).scalars().all()
    by_country: dict[str, list[Player]] = {}
    for p in players:
        if p.country:
            by_country.setdefault(p.country.strip(), []).append(p)
    base = pcc.pick(config.player_career_level_ratings, 1, 74)
    nations = []
    for name, members in by_country.items():
        squad = pcc.squad_from_cards(name, members, base)
        nations.append({"key": f"nation:{name}", "name": name, "rating": pcc.avg_rating(squad), "squad": squad})
    mine = next((n for n in nations if n["name"] == country), None)
    if mine is None:
        squad = pcc.academy_squad(f"nation:{country}", base)
        mine = {"key": f"nation:{country}", "name": country, "rating": pcc.avg_rating(squad), "squad": squad}
    others = sorted((n for n in nations if n["name"] != country), key=lambda n: -n["rating"])[: CUP_TEAMS - 1]
    taken = {country, *(n["name"] for n in others)}
    for name in DEFAULT_COUNTRIES:
        if len(others) >= CUP_TEAMS - 1:
            break
        if name in taken:
            continue
        squad = pcc.academy_squad(f"nation:{name}", base + random.Random(pcc._seed(name)).randint(-4, 4))
        others.append({"key": f"nation:{name}", "name": name, "rating": pcc.avg_rating(squad), "squad": squad})
    return [mine, *others]


def national_status(mp: MyPlayer, config) -> dict:
    need = config.player_career_national_prestige
    return {
        "country": mp.country, "prestige_needed": need,
        "called_up": bool(mp.country) and (mp.reputation or 0) >= need,
    }


async def ensure_national(db: AsyncSession, user_id: int, config, now: Optional[datetime] = None) -> Optional[PlayerCareerCup]:
    """Creates this two-week window's national tournament for a called-up
    player (once per window). Commits when created."""
    now = now or datetime.now(timezone.utc)
    mp = await my_player_service.get_my_player(db, user_id)
    if mp is None or not national_status(mp, config)["called_up"]:
        return None
    window = national_window(local_today(now))
    exists = (await db.execute(select(PlayerCareerCup.id).where(
        PlayerCareerCup.user_id == user_id, PlayerCareerCup.kind == "national", PlayerCareerCup.window_key == window,
    ))).first()
    if exists:
        return None
    teams = [_team(i, n) for i, n in enumerate(await _nation_teams(db, mp.country, config))]
    cup = PlayerCareerCup(
        user_id=user_id, kind="national", window_key=window, status="active",
        state=_new_state("national", f"{CUP_TITLES['national']} · {mp.country}", teams, now),
    )
    try:
        async with db.begin_nested():
            db.add(cup)
            await db.flush()
    except IntegrityError:
        return None
    await notify(
        db, user_id, NotificationType.player_career_event, f"Вызов в сборную: {mp.country} 🌍",
        "Тебя вызвали на турнир сборных — 1/4 финала уже скоро",
        related_object_type="player_career_cup", related_object_id=cup.id,
    )
    await db.commit()
    return cup


def _rewards(kind: str, config) -> list[int]:
    return list((config.player_career_cl_rewards if kind == "cl" else config.player_career_national_rewards) or [])


async def _play_cup_round(db: AsyncSession, cup: PlayerCareerCup, config) -> None:
    from app.services import player_career_service as pcs

    state = copy.deepcopy(cup.state)
    r = cup.rounds_played
    teams = state["teams"]
    mine = await my_player_service.engine_card(db, cup.user_id, config)
    my_id = mine.id if mine is not None else None
    rng = random.Random(cup.id * 7741 + r)
    results, winners = [], []
    my_entry = None
    for home, away in state["pairs"][r]:
        side_h = pcs._side(teams[home], mine if home == 0 else None, config)
        side_a = pcs._side(teams[away], mine if away == 0 else None, config)
        match = tournament_match_engine.simulate_match(
            side_h[0], side_a[0], side_h[1], side_a[1], config, teams[home]["name"], teams[away]["name"],
        )
        hs, as_ = match.score_a, match.score_b
        pens = hs == as_
        winner = (home if rng.random() < 0.5 else away) if pens else (home if hs > as_ else away)
        entry = {"home": home, "away": away, "hs": hs, "as": as_, "pens": pens, "winner": winner}
        results.append(entry)
        winners.append(winner)
        if 0 in (home, away):
            my_entry = (entry, match.event_log, "a" if home == 0 else "b")
    state["results"].append(results)

    entry, events, my_side = my_entry
    own, opp = (entry["hs"], entry["as"]) if my_side == "a" else (entry["as"], entry["hs"])
    goals = sum(1 for e in events if e.get("event_type") == "goal" and e.get("team") == my_side
                and (e.get("payload") or {}).get("shooter_id") == my_id and my_id is not None)
    assists = sum(1 for e in events if e.get("event_type") == "goal" and e.get("team") == my_side
                  and (e.get("payload") or {}).get("assist_id") == my_id and my_id is not None)
    won = entry["winner"] == 0
    line = my_player_service.category_of(mine.player.position) if mine is not None else "FWD"
    rating = pcs._match_rating(goals, assists, own + (1 if won and entry["pens"] else 0), opp, rng, line) if mine else None
    opponent = teams[entry["away"] if my_side == "a" else entry["home"]]["name"]
    state["my_rounds"][str(r)] = {
        "played": mine is not None, "goals": goals, "assists": assists, "rating": rating, "own": own, "opp": opp,
        "pens": entry["pens"], "won": won, "opponent": opponent,
    }
    rewards = _rewards(cup.kind, config)
    reward = pcc.pick(rewards, r) if won and r < len(rewards) else 0
    if reward:
        locked = await wallet_service.lock_user_for_update(db, cup.user_id)
        await wallet_service.credit_coins(
            db, locked, reward, TransactionType.player_career_reward, f"{state['title']}: {ROUND_LABELS[r]}",
            related_object_type="player_career_cup", related_object_id=cup.id,
        )
        cup.coins_earned += reward
    at = ensure_aware(datetime.fromisoformat(state["schedule"][r])) if r < len(state["schedule"]) else datetime.now(timezone.utc)
    if mine is not None:
        locked = await wallet_service.lock_user_for_update(db, cup.user_id)
        my_player_service.add_xp(
            locked, config.player_career_match_xp, config, bonus_pct=await my_player_service.xp_bonus_pct(db, cup.user_id),
        )
        await record_match(db, cup.user_id, at, goals, assists, rating, clean_sheet=opp == 0, line=line)
    label = ROUND_LABELS[r]
    if not won:
        state["alive"] = False
    elif r == CUP_ROUNDS - 1:
        state["won"] = True
    else:
        state["pairs"].append([[winners[i], winners[i + 1]] for i in range(0, len(winners), 2)])
    personal = (f" · голы: {goals}" if goals else "") + (f" · передачи: {assists}" if assists else "")
    await notify(
        db, cup.user_id, NotificationType.player_career_event,
        f"{state['title']}, {label}: {'проход дальше' if won and r < CUP_ROUNDS - 1 else 'победа в турнире!' if won else 'вылет'}",
        f"{own}:{opp}{' (пен.)' if entry['pens'] else ''} против «{opponent}»{personal}" + (f" · +{reward} монет" if reward else ""),
        related_object_type="player_career_cup", related_object_id=cup.id,
    )
    cup.rounds_played = r + 1
    if not state["alive"] or state["won"]:
        cup.status = "finished"
        cup.finished_at = datetime.now(timezone.utc)
        if state["won"]:
            prestige = config.player_career_cl_prestige if cup.kind == "cl" else config.player_career_national_win_prestige
            mp = (await db.execute(select(MyPlayer).where(MyPlayer.user_id == cup.user_id).with_for_update())).scalar_one_or_none()
            if mp is not None:
                mp.reputation = (mp.reputation or 0) + prestige
                stats = {**(mp.career_stats or {})}
                stats[f"{cup.kind}_titles"] = stats.get(f"{cup.kind}_titles", 0) + 1
                mp.career_stats = stats
            name = await pcs._grant_trophy(db, cup.user_id, CUP_TROPHIES[cup.kind], state["title"])
            state["award"] = name
    cup.state = state
    flag_modified(cup, "state")


async def resolve_cup(db: AsyncSession, cup_id: int, now: Optional[datetime] = None) -> int:
    from app.services.game_config_service import get_config

    now = now or datetime.now(timezone.utc)
    config = await get_config(db)
    cup = (await db.execute(
        select(PlayerCareerCup).where(PlayerCareerCup.id == cup_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    played = 0
    while cup is not None and cup.status == "active" and cup.rounds_played < CUP_ROUNDS:
        schedule = (cup.state or {}).get("schedule") or []
        at = ensure_aware(datetime.fromisoformat(schedule[cup.rounds_played])) if cup.rounds_played < len(schedule) else None
        if at is None or at > now:
            break
        await _play_cup_round(db, cup, config)
        played += 1
    await db.commit()
    return played


async def resolve_all_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    ids = (await db.execute(select(PlayerCareerCup.id).where(PlayerCareerCup.status == "active"))).scalars().all()
    total = sum([await resolve_cup(db, cup_id, now) for cup_id in ids])
    await award_golden_ball(db, now)
    return total


def cup_out(cup: PlayerCareerCup) -> dict:
    state = cup.state or {}
    teams = state.get("teams") or []
    rounds = []
    for r, pairs in enumerate(state.get("pairs") or []):
        played = (state.get("results") or [])[r] if r < len(state.get("results") or []) else None
        rounds.append({
            "label": ROUND_LABELS[r] if r < len(ROUND_LABELS) else f"Раунд {r + 1}",
            "at": (state.get("schedule") or [None] * CUP_ROUNDS)[r] if r < len(state.get("schedule") or []) else None,
            "matches": [
                {
                    "home": teams[h]["name"], "away": teams[a]["name"], "home_mine": h == 0, "away_mine": a == 0,
                    **({"hs": m["hs"], "away_score": m["as"], "pens": m["pens"], "winner_mine": m["winner"] == 0,
                        "home_won": m["winner"] == h} if (m := next((x for x in played or [] if x["home"] == h), None)) else {}),
                }
                for h, a in pairs
            ],
            "me": (state.get("my_rounds") or {}).get(str(r)),
        })
    next_at = None
    if cup.status == "active" and cup.rounds_played < len(state.get("schedule") or []):
        next_at = state["schedule"][cup.rounds_played]
    return {
        "id": cup.id, "kind": cup.kind, "title": state.get("title") or CUP_TITLES.get(cup.kind, ""), "status": cup.status,
        "rounds_played": cup.rounds_played, "next_round_at": next_at, "alive": state.get("alive", True),
        "won": state.get("won", False), "award": state.get("award"), "coins_earned": cup.coins_earned, "rounds": rounds,
        "my_team": teams[0]["name"] if teams else None,
    }


async def cups_view(db: AsyncSession, user_id: int) -> list[dict]:
    """The active cups, else the latest of each kind."""
    rows = (await db.execute(
        select(PlayerCareerCup).where(PlayerCareerCup.user_id == user_id).order_by(PlayerCareerCup.id.desc()).limit(10)
    )).scalars().all()
    shown: dict[str, PlayerCareerCup] = {}
    for cup in rows:
        if cup.kind not in shown or (cup.status == "active" and shown[cup.kind].status != "active"):
            shown[cup.kind] = cup
    return [cup_out(c) for c in sorted(shown.values(), key=lambda c: (c.status != "active", -c.id))]
