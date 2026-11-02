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
- «Золотой мяч»: the best of the month by a form index measured against
  the player's own line (score_of): 50 x average rating / the line's average
  rating + 50 x contribution per match / the line's average contribution
  (goals, assists and clean sheets at LINE_WEIGHTS). An average player of any
  line scores ~100, so a keeper who stands out among keepers beats a forward
  who is merely good among forwards. Line averages are shrunk towards
  LINE_PRIOR (LINE_PRIOR_WEIGHT virtual players) so a thin line isn't decided
  by one or two players. At least config min matches. Awarded once per month
  (PlayerCareerGoldenBall's primary key) when the next month starts.
- Призы месяца (MONTH_AWARDS): «Золотая бутса» (goals), «Король передач»
  (assists), «Золотая перчатка» (keepers, clean sheets) and «Лучший
  защитник» (defenders, form index) — same minimum of matches, awarded with
  the «Золотой мяч» once per (month, code) (PlayerCareerMonthAward's key).
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
from app.models.player_career import PlayerCareerCup, PlayerCareerGoldenBall, PlayerCareerMonthAward, PlayerCareerMonthStat
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
# Typical month of each line (per match): the shrinkage target of the line
# averages in score_of.
LINE_PRIOR = {
    "FWD": {"rating": 7.0, "contribution": 2.3},
    "MID": {"rating": 6.9, "contribution": 2.4},
    "DEF": {"rating": 6.9, "contribution": 2.1},
    "GK": {"rating": 6.9, "contribution": 2.1},
}
LINE_PRIOR_WEIGHT = 4
# Monthly awards besides the «Золотой мяч»: code -> (trophy, title, line or
# None for every line, the stat it is decided by).
MONTH_AWARDS = {
    "golden_boot": ("player_career_golden_boot", "Золотая бутса", None, "goals"),
    "top_assist": ("player_career_top_assist", "Король передач", None, "assists"),
    "golden_glove": ("player_career_golden_glove", "Золотая перчатка", "GK", "clean_sheets"),
    "best_defender": ("player_career_best_defender", "Лучший защитник", "DEF", "score"),
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
    clean_sheet: bool = False, line: str = "FWD", won: bool = False,
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
    from app.services import my_player_extras
    from app.services.player_career_life import record_week

    await record_week(db, user_id, at, goals, assists, rating, clean_sheet)
    # «Спонсор» goals: every career match (league, cups, friends, «Менеджер»).
    await my_player_extras.progress(db, user_id, "career_match", 1, at)
    await my_player_extras.progress(db, user_id, "career_goal", goals, at)
    if won:
        await my_player_extras.progress(db, user_id, "career_win", 1, at)


def _avg_rating(row: PlayerCareerMonthStat) -> float:
    return row.rating_sum / row.matches if row.matches else 0


def _contribution(row: PlayerCareerMonthStat) -> float:
    """Points per match: goals, assists and clean sheets at the line's weights."""
    if not row.matches:
        return 0
    w = LINE_WEIGHTS.get(row.line or "FWD", LINE_WEIGHTS["FWD"])
    return (row.goals * w["goals"] + row.assists * w["assists"] + (row.clean_sheets or 0) * w["clean_sheets"]) / row.matches


def line_baselines(rows: list[PlayerCareerMonthStat]) -> dict[str, dict[str, float]]:
    """Each line's average rating and contribution among the given (eligible)
    month rows, shrunk towards LINE_PRIOR."""
    out = {}
    for line, prior in LINE_PRIOR.items():
        mine = [r for r in rows if (r.line or "FWD") == line]
        k = LINE_PRIOR_WEIGHT
        out[line] = {
            "rating": (sum(_avg_rating(r) for r in mine) + k * prior["rating"]) / (len(mine) + k),
            "contribution": (sum(_contribution(r) for r in mine) + k * prior["contribution"]) / (len(mine) + k),
        }
    return out


def score_of(row: PlayerCareerMonthStat, baselines: Optional[dict] = None) -> float:
    """Form index against the player's own line: ~100 is an average month."""
    base = (baselines or LINE_PRIOR).get(row.line or "FWD", LINE_PRIOR["FWD"])
    rating = _avg_rating(row) / base["rating"] if base["rating"] else 0
    contribution = _contribution(row) / base["contribution"] if base["contribution"] else 0
    return round(50 * rating + 50 * contribution, 1)


async def _eligible(db: AsyncSession, key: str, config) -> list[tuple[PlayerCareerMonthStat, User]]:
    rows = (await db.execute(
        select(PlayerCareerMonthStat, User).join(User, User.id == PlayerCareerMonthStat.user_id)
        .where(PlayerCareerMonthStat.month == key, PlayerCareerMonthStat.matches >= config.player_career_golden_ball_min_matches)
    )).all()
    return [(r, u) for r, u in rows]


async def _month_table(
    db: AsyncSession, key: str, config, limit: Optional[int] = 20,
) -> tuple[list[tuple[PlayerCareerMonthStat, User]], dict]:
    """The month's «Золотой мяч» race and the line baselines it was scored by."""
    eligible = await _eligible(db, key, config)
    baselines = line_baselines([r for r, _ in eligible])
    ranked = sorted(eligible, key=lambda ru: (-score_of(ru[0], baselines), ru[0].user_id))
    return (ranked[:limit] if limit else ranked), baselines


def award_value(code: str, row: PlayerCareerMonthStat, baselines: dict) -> float:
    stat = MONTH_AWARDS[code][3]
    return score_of(row, baselines) if stat == "score" else float(getattr(row, stat) or 0)


def award_race(code: str, eligible: list[tuple[PlayerCareerMonthStat, User]], baselines: dict) -> list[tuple[PlayerCareerMonthStat, User, float]]:
    """Candidates of a month award, best first (ties: higher average rating,
    then the earlier player); a counting stat needs at least one."""
    _, _, line, stat = MONTH_AWARDS[code]
    rows = [(r, u, award_value(code, r, baselines)) for r, u in eligible if line is None or (r.line or "FWD") == line]
    if stat != "score":
        rows = [x for x in rows if x[2] > 0]
    return sorted(rows, key=lambda x: (-x[2], -_avg_rating(x[0]), x[0].user_id))


async def _prize(db: AsyncSession, user_id: int, coins: int, prestige: int, title: str, label: str, related: str) -> None:
    locked = await wallet_service.lock_user_for_update(db, user_id)
    if coins > 0:
        await wallet_service.credit_coins(
            db, locked, coins, TransactionType.player_career_reward, f"{title} · {label}", related_object_type=related,
        )
    mp = await my_player_service.get_my_player(db, user_id)
    if mp is not None:
        mp.reputation = (mp.reputation or 0) + prestige


def award_text(code: str, value: float) -> str:
    stat = MONTH_AWARDS[code][3]
    n = int(value)
    if stat == "goals":
        return f"{n} голов"
    if stat == "assists":
        return f"{n} передач"
    if stat == "clean_sheets":
        return f"{n} сухих матчей"
    return f"индекс формы {value:g}"


async def award_golden_ball(db: AsyncSession, now: Optional[datetime] = None) -> Optional[int]:
    """Awards last month's «Золотой мяч» and the month awards once each (a
    row is written even with no winner). Returns the «Золотой мяч» winner's
    user id when this call awarded it. Commits."""
    from app.services.game_config_service import get_config
    from app.services.player_career_service import _grant_trophy

    now = now or datetime.now(timezone.utc)
    local = ensure_aware(now).astimezone(app_timezone())
    previous = month_key(local.replace(day=1) - timedelta(days=1))
    ball_done = await db.get(PlayerCareerGoldenBall, previous) is not None
    done_awards = set((await db.execute(
        select(PlayerCareerMonthAward.code).where(PlayerCareerMonthAward.month == previous)
    )).scalars().all())
    if ball_done and done_awards >= set(MONTH_AWARDS):
        return None
    config = await get_config(db)
    eligible = await _eligible(db, previous, config)
    baselines = line_baselines([r for r, _ in eligible])
    label = month_label(previous)
    winner_id = None

    if not ball_done:
        ranked = sorted(eligible, key=lambda ru: (-score_of(ru[0], baselines), ru[0].user_id))
        winner = ranked[0] if ranked else None
        row = PlayerCareerGoldenBall(month=previous, user_id=None, score=0)
        if winner:
            stat, user = winner
            row.user_id = user.id
            row.score = score_of(stat, baselines)
            row.goals, row.assists = stat.goals, stat.assists
            row.avg_rating = round(_avg_rating(stat), 2)
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            winner = None  # someone else just awarded it
        if winner:
            stat, user = winner
            winner_id = user.id
            await _grant_trophy(db, user.id, GOLDEN_BALL_TROPHY, f"{label}: {stat.goals} голов, оценка {row.avg_rating}")
            await _prize(
                db, user.id, config.player_career_golden_ball_coins, config.player_career_golden_ball_prestige,
                "Золотой мяч", label, "player_career_golden_ball",
            )
            await notify(
                db, user.id, NotificationType.player_career_event, "🏆 Ты выиграл «Золотой мяч»!",
                f"Лучший игрок за {label.lower()}: +{config.player_career_golden_ball_coins} монет и "
                f"+{config.player_career_golden_ball_prestige} престижа",
            )

    for code, (trophy, title, _, _) in MONTH_AWARDS.items():
        if code in done_awards:
            continue
        race = award_race(code, eligible, baselines)
        best = race[0] if race else None
        row = PlayerCareerMonthAward(
            month=previous, code=code, user_id=best[1].id if best else None,
            value=best[2] if best else 0, avg_rating=round(_avg_rating(best[0]), 2) if best else 0,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
        except IntegrityError:
            continue
        if best is None:
            continue
        _, user, value = best
        await _grant_trophy(db, user.id, trophy, f"{label}: {award_text(code, value)}")
        await _prize(db, user.id, config.player_career_award_coins, config.player_career_award_prestige, title, label, trophy)
        await notify(
            db, user.id, NotificationType.player_career_event, f"🏆 «{title}» за {label.lower()}!",
            f"{award_text(code, value).capitalize()}: +{config.player_career_award_coins} монет и "
            f"+{config.player_career_award_prestige} престижа",
        )
    await db.commit()
    return winner_id


async def golden_ball_view(db: AsyncSession, user: User, config, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    key = month_key(now)
    ranked, baselines = await _month_table(db, key, config, limit=None)
    mine = (await db.execute(
        select(PlayerCareerMonthStat).where(PlayerCareerMonthStat.user_id == user.id, PlayerCareerMonthStat.month == key)
    )).scalar_one_or_none()
    my_place = next((i + 1 for i, (r, _) in enumerate(ranked) if r.user_id == user.id), None)
    winners = (await db.execute(
        select(PlayerCareerGoldenBall, User).outerjoin(User, User.id == PlayerCareerGoldenBall.user_id)
        .where(PlayerCareerGoldenBall.user_id.is_not(None)).order_by(PlayerCareerGoldenBall.month.desc()).limit(6)
    )).all()

    def name(owner: Optional[User]) -> str:
        return (owner.first_name or owner.username or "Игрок") if owner else "—"

    def entry(stat: PlayerCareerMonthStat, owner: User, place: int) -> dict:
        return {
            "place": place, "user_id": owner.id, "user_name": name(owner),
            "is_me": owner.id == user.id, "matches": stat.matches, "goals": stat.goals, "assists": stat.assists,
            "clean_sheets": stat.clean_sheets or 0, "line": stat.line or "FWD",
            "avg_rating": round(_avg_rating(stat), 2) if stat.matches else None, "score": score_of(stat, baselines),
        }

    last_key = month_key(ensure_aware(now).astimezone(app_timezone()).replace(day=1) - timedelta(days=1))
    last = {
        a.code: (a, u) for a, u in (await db.execute(
            select(PlayerCareerMonthAward, User).outerjoin(User, User.id == PlayerCareerMonthAward.user_id)
            .where(PlayerCareerMonthAward.month == last_key)
        )).all()
    }
    mine_eligible = mine is not None and mine.matches >= config.player_career_golden_ball_min_matches
    awards = []
    for code, (trophy, title, line, stat_name) in MONTH_AWARDS.items():
        race = award_race(code, ranked, baselines)
        leader = race[0] if race else None
        my_line = mine is not None and (line is None or (mine.line or "FWD") == line)
        prev = last.get(code)
        awards.append({
            "code": code, "trophy": trophy, "title": title, "line": line, "stat": stat_name,
            "leader": {"user_name": name(leader[1]), "is_me": leader[1].id == user.id, "value": leader[2]} if leader else None,
            "my_value": award_value(code, mine, baselines) if my_line else None,
            "my_place": next((i + 1 for i, x in enumerate(race) if x[0].user_id == user.id), None) if mine_eligible else None,
            "last": {
                "month_label": month_label(last_key), "user_name": name(prev[1]),
                "is_me": prev[1].id == user.id, "value": prev[0].value,
            } if prev and prev[1] is not None else None,
        })

    return {
        "month": key, "month_label": month_label(key), "min_matches": config.player_career_golden_ball_min_matches,
        "prize_coins": config.player_career_golden_ball_coins, "prize_prestige": config.player_career_golden_ball_prestige,
        "award_coins": config.player_career_award_coins, "award_prestige": config.player_career_award_prestige,
        "weights": LINE_WEIGHTS,
        "baselines": {line: {k: round(v, 2) for k, v in b.items()} for line, b in baselines.items()},
        "table": [entry(r, u, i + 1) for i, (r, u) in enumerate(ranked[:20])],
        "me": entry(mine, user, my_place or 0) if mine is not None else None,
        "awards": awards,
        "winners": [
            {"month": g.month, "month_label": month_label(g.month), "user_name": name(u),
             "is_me": bool(u and u.id == user.id), "score": g.score, "goals": g.goals, "assists": g.assists,
             "avg_rating": g.avg_rating}
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
        await record_match(db, cup.user_id, at, goals, assists, rating, clean_sheet=opp == 0, line=line, won=won)
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
