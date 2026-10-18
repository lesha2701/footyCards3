"""«Карьера игрока»: life around the matches.

- Role & the coach's trust (MyPlayer.trust 0-100, reset to 50 at a new
  club): bench when his match rating is more than config.player_career_bench_gap
  below the club average and the trust is under trust_starter (a bench
  player comes on in bench_play_pct% of matches), or whenever the trust has
  sunk under 20; captain = a starter at or above the club average with
  trust >= trust_captain (+captain_salary_pct% salary, +1 prestige per win).
  Ratings, objectives and story events move the trust.
- Injuries: below config.player_career_injury_freshness a match may injure
  him for 1-3 league rounds; healed for coins or Stars.
- Story events between rounds (one at a time, at most one per
  config.player_career_event_every rounds) with choices that move prestige,
  trust, coins, freshness or XP (amounts are multiples of the config base).
- Headlines for every league match (the «Газета» feed).
- Hall of Fame: per-club records of every player (PlayerCareerClubRecord).
- Weekly rankings (scorers, ratings) and prestige; weekly tasks; the daily
  career chest; «Карьера Pro» helpers.
"""
import random
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.enums import TransactionType
from app.models.my_player import MyPlayer
from app.models.player_career import PlayerCareerClubRecord, PlayerCareerWeeklyClaim, PlayerCareerWeekStat
from app.models.user import User

TRUST_START = 50
TRUST_BENCH_ANYWAY = 20


# --- «Карьера Pro» ----------------------------------------------------------------------

def is_pro(mp: Optional[MyPlayer], now: Optional[datetime] = None) -> bool:
    if mp is None or mp.pro_until is None:
        return False
    return ensure_aware(mp.pro_until) > (now or datetime.now(timezone.utc))


def career_xp_bonus(mp: Optional[MyPlayer], config) -> int:
    return config.player_career_pro_xp_pct if is_pro(mp) else 0


# --- role & trust ------------------------------------------------------------------------

def role_of(mp: MyPlayer, my_rating: int, club_rating: int, config) -> str:
    trust = mp.trust if mp.trust is not None else TRUST_START
    gap = my_rating - club_rating
    if trust < TRUST_BENCH_ANYWAY:
        return "bench"
    if gap < -config.player_career_bench_gap and trust < config.player_career_trust_starter:
        return "bench"
    if gap >= 0 and trust >= config.player_career_trust_captain:
        return "captain"
    return "starter"


ROLE_LABELS = {"bench": "Запасной", "starter": "Основной", "captain": "Капитан"}


def move_trust(mp: MyPlayer, delta: int) -> None:
    mp.trust = max(0, min(100, (mp.trust if mp.trust is not None else TRUST_START) + delta))


def trust_after_match(rating: Optional[float]) -> int:
    if rating is None:
        return 0
    return 4 if rating >= 7.5 else 2 if rating >= 6.8 else -3 if rating < 6.0 else 0


# --- injuries ---------------------------------------------------------------------------

def injury_roll(freshness_before: int, config, rng: random.Random) -> int:
    """League rounds he'll miss (0 = fine)."""
    threshold = config.player_career_injury_freshness
    if freshness_before >= threshold or threshold <= 0:
        return 0
    pct = config.player_career_injury_max_pct * (threshold - freshness_before) / threshold
    return rng.randint(1, 3) if rng.random() * 100 < pct else 0


# --- story events -----------------------------------------------------------------------

# Effects: prestige / coins / XP are multiples of config.player_career_event_prestige /
# event_coins / my_player_xp_per_reward; trust and freshness are absolute.
EVENTS = {
    "interview": {
        "title": "Интервью после матча",
        "text": "Журналист спрашивает о твоих амбициях. Что ответишь?",
        "choices": [
            ("team", "«Главное — команда»", {"trust": 6}),
            ("star", "«Я лучший в этой лиге»", {"prestige": 2, "trust": -6}),
        ],
    },
    "fans": {
        "title": "Фанаты недовольны",
        "text": "После неудачной серии фанаты освистывают команду у базы.",
        "choices": [
            ("talk", "Выйти к фанатам и поговорить", {"prestige": 1, "trust": 3}),
            ("ignore", "Уехать с базы молча", {"trust": -2}),
        ],
    },
    "ad": {
        "title": "Рекламный контракт",
        "text": "Бренд спортивных напитков предлагает съёмку в выходной.",
        "choices": [
            ("sign", "Согласиться", {"coins": 3, "freshness": -15}),
            ("rest", "Отдохнуть перед матчем", {"freshness": 15}),
        ],
    },
    "charity": {
        "title": "Благотворительный матч",
        "text": "Детская школа зовёт сыграть с ними и провести мастер-класс.",
        "choices": [
            ("go", "Поехать", {"prestige": 2, "freshness": -10}),
            ("donate", "Отправить форму и подарки", {"coins": -1, "prestige": 1}),
        ],
    },
    "extra": {
        "title": "Дополнительная тренировка",
        "text": "Тренер предлагает остаться после тренировки и поработать над ударом.",
        "choices": [
            ("stay", "Остаться", {"xp": 4, "freshness": -12, "trust": 3}),
            ("home", "Восстановиться", {"freshness": 10}),
        ],
    },
    "rumour": {
        "title": "Слухи о трансфере",
        "text": "Газеты пишут, что тобой интересуется клуб посильнее.",
        "choices": [
            ("deny", "«Я счастлив здесь»", {"trust": 5}),
            ("tease", "«Посмотрим…»", {"prestige": 2, "trust": -4}),
        ],
    },
    "night": {
        "title": "Приглашение на вечеринку",
        "text": "Друзья зовут отметить победу до утра.",
        "choices": [
            ("party", "Пойти", {"prestige": 1, "freshness": -20, "trust": -3}),
            ("sleep", "Лечь спать пораньше", {"freshness": 8, "trust": 2}),
        ],
    },
}


def event_out(event: dict, config) -> dict:
    spec = EVENTS[event["code"]]
    return {
        "id": event["id"], "code": event["code"], "title": spec["title"], "text": spec["text"],
        "status": event["status"], "answer": event.get("answer"),
        "choices": [{"key": k, "label": label, "effects": scale(effects, config)} for k, label, effects in spec["choices"]],
    }


def scale(effects: dict, config) -> dict:
    out = dict(effects)
    if "prestige" in out:
        out["prestige"] *= config.player_career_event_prestige
    if "coins" in out:
        out["coins"] *= config.player_career_event_coins
    if "xp" in out:
        out["xp"] *= config.my_player_xp_per_reward
    return out


def maybe_new_event(state: dict, round_index: int, config, rng: random.Random) -> Optional[dict]:
    """One pending event at a time, at most one per event_every rounds."""
    events = state.setdefault("events", [])
    if any(e["status"] == "open" for e in events):
        return None
    last = max((e["round"] for e in events), default=-99)
    if round_index - last < max(1, config.player_career_event_every) or rng.random() > 0.55:
        return None
    used = {e["code"] for e in events}
    pool = [code for code in EVENTS if code not in used] or list(EVENTS)
    event = {"id": len(events) + 1, "code": rng.choice(pool), "round": round_index, "status": "open", "answer": None}
    events.append(event)
    return event


# --- headlines --------------------------------------------------------------------------

CELEBRATIONS = {"cel_siu": "фирменным «Сиу!»", "cel_plane": "«самолётиком»", "cel_heart": "сердечком для фанатов", "cel_dance": "танцем у флажка"}


def headline(name: str, club: str, opponent: str, own: int, opp: int, me: dict, celebration: Optional[str]) -> str:
    """The «Газета» line for the player's match. The name always stays in the
    nominative — player names can't be declined reliably."""
    goals, assists = me.get("goals", 0), me.get("assists", 0)
    score = f"«{club}» — «{opponent}» {own}:{opp}"
    if not me.get("played"):
        if me.get("injured"):
            return f"{name} лечит травму: {score}"
        return f"{name} остался на скамейке: {score}"
    cel = f" и празднует {CELEBRATIONS[celebration]}" if goals and celebration in CELEBRATIONS else ""
    if goals >= 3:
        return f"{name} оформляет хет-трик{cel}! {score}"
    if goals and own > opp:
        return f"{name} забивает{cel} — {score}"
    if goals:
        return f"{name} забил{cel}, но победы нет: {score}"
    if assists and own > opp:
        return f"{name} отдаёт решающий пас: {score}"
    if me.get("stops") and opp == 0:
        return f"{name} — стена! Сухой матч: {score}"
    if (me.get("rating") or 0) < 5.6:
        return f"{name} провёл неудачный вечер: {score}"
    if own > opp:
        return f"{name} в основе, «{club}» побеждает: {own}:{opp} с «{opponent}»"
    return f"{name} не смог переломить игру: {score}"


# --- week stats, rankings, weekly tasks ---------------------------------------------------

def week_key(at: datetime) -> str:
    local = ensure_aware(at).astimezone(app_timezone())
    year, week, _ = local.isocalendar()
    return f"{year}-W{week:02d}"


async def record_week(db: AsyncSession, user_id: int, at: datetime, goals: int, assists: int, rating: float, clean_sheet: bool) -> None:
    key = week_key(at)
    row = (await db.execute(
        select(PlayerCareerWeekStat).where(PlayerCareerWeekStat.user_id == user_id, PlayerCareerWeekStat.week == key)
    )).scalar_one_or_none()
    if row is None:
        row = PlayerCareerWeekStat(user_id=user_id, week=key, matches=0, goals=0, assists=0, clean_sheets=0, rating_sum=0)
        db.add(row)
    row.matches += 1
    row.goals += goals
    row.assists += assists
    row.clean_sheets += int(clean_sheet)
    row.rating_sum += float(rating)


def _name(user: User) -> str:
    return user.first_name or user.username or "Игрок"


async def rankings(db: AsyncSession, user: User, now: Optional[datetime] = None) -> dict:
    key = week_key(now or datetime.now(timezone.utc))
    rows = (await db.execute(
        select(PlayerCareerWeekStat, User).join(User, User.id == PlayerCareerWeekStat.user_id)
        .where(PlayerCareerWeekStat.week == key)
    )).all()

    def entry(stat: PlayerCareerWeekStat, owner: User, place: int, value) -> dict:
        return {"place": place, "user_id": owner.id, "user_name": _name(owner), "is_me": owner.id == user.id,
                "value": value, "matches": stat.matches}

    scorers = sorted(rows, key=lambda r: (-r[0].goals, -r[0].assists, r[0].user_id))
    rated = sorted(
        (r for r in rows if r[0].matches >= 4), key=lambda r: (-(r[0].rating_sum / r[0].matches), r[0].user_id),
    )
    prestige = (await db.execute(
        select(MyPlayer, User).join(User, User.id == MyPlayer.user_id).order_by(MyPlayer.reputation.desc(), MyPlayer.id).limit(10)
    )).all()
    return {
        "week": key,
        "scorers": [entry(s, u, i + 1, s.goals) for i, (s, u) in enumerate(scorers[:10]) if s.goals > 0],
        "ratings": [entry(s, u, i + 1, round(s.rating_sum / s.matches, 2)) for i, (s, u) in enumerate(rated[:10])],
        "prestige": [
            {"place": i + 1, "user_id": u.id, "user_name": _name(u), "is_me": u.id == user.id, "value": mp.reputation or 0,
             "player_name": mp.name}
            for i, (mp, u) in enumerate(prestige)
        ],
    }


def weekly_tasks_spec(config) -> list[dict]:
    coins = list(config.player_career_weekly_coins or [0, 0, 0]) + [0, 0, 0]
    return [
        {"code": "goals", "label": f"Забей {config.player_career_weekly_goals} голов", "target": config.player_career_weekly_goals, "coins": coins[0]},
        {"code": "matches", "label": f"Сыграй {config.player_career_weekly_matches} матчей", "target": config.player_career_weekly_matches, "coins": coins[1]},
        {"code": "rating", "label": f"Средняя оценка {config.player_career_weekly_rating_x10 / 10:.1f}+ (от 5 матчей)",
         "target": config.player_career_weekly_rating_x10 / 10, "coins": coins[2]},
    ]


def _task_value(code: str, stat: Optional[PlayerCareerWeekStat]):
    if stat is None:
        return 0
    if code == "goals":
        return stat.goals
    if code == "matches":
        return stat.matches
    return round(stat.rating_sum / stat.matches, 2) if stat.matches >= 5 else 0


async def weekly_tasks(db: AsyncSession, user_id: int, config, now: Optional[datetime] = None) -> dict:
    key = week_key(now or datetime.now(timezone.utc))
    stat = (await db.execute(
        select(PlayerCareerWeekStat).where(PlayerCareerWeekStat.user_id == user_id, PlayerCareerWeekStat.week == key)
    )).scalar_one_or_none()
    claimed = set((await db.execute(
        select(PlayerCareerWeeklyClaim.code).where(PlayerCareerWeeklyClaim.user_id == user_id, PlayerCareerWeeklyClaim.week == key)
    )).scalars().all())
    tasks = []
    for t in weekly_tasks_spec(config):
        value = _task_value(t["code"], stat)
        tasks.append({**t, "value": value, "done": value >= t["target"], "claimed": t["code"] in claimed})
    return {"week": key, "tasks": tasks}


async def claim_weekly(db: AsyncSession, user: User, code: str, config, now: Optional[datetime] = None) -> int:
    from app.services import wallet_service

    view = await weekly_tasks(db, user.id, config, now)
    task = next((t for t in view["tasks"] if t["code"] == code), None)
    if task is None:
        raise NotFoundError("Задание не найдено")
    if not task["done"]:
        raise ConflictError("Задание ещё не выполнено")
    if task["claimed"]:
        raise ConflictError("Награда уже получена")
    locked = await wallet_service.lock_user_for_update(db, user.id)
    db.add(PlayerCareerWeeklyClaim(user_id=user.id, week=view["week"], code=code))
    await db.flush()  # the unique constraint guards a double claim
    if task["coins"] > 0:
        await wallet_service.credit_coins(
            db, locked, task["coins"], TransactionType.player_career_reward, f"Карьера игрока: задание недели «{task['label']}»",
            related_object_type="player_career_weekly",
        )
    await db.commit()
    return task["coins"]


# --- daily chest ---------------------------------------------------------------------------

async def open_chest(db: AsyncSession, user: User, config, now: Optional[datetime] = None) -> dict:
    """Once per local day: coins, sometimes a skill token of the player's skill."""
    from app.services import my_player_service, wallet_service
    from app.services.card_skill_catalog import SKILL_DEFINITIONS
    from app.services.card_skill_service import _lock_token_row

    today = local_today(now)
    locked = await wallet_service.lock_user_for_update(db, user.id)
    mp = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id == user.id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if mp is None:
        raise NotFoundError("Сначала создай своего игрока")
    if mp.chest_day == today:
        raise ConflictError("Сундук на сегодня уже открыт — приходи завтра")
    rng = random.Random()
    low, high = sorted((config.player_career_chest_coins_min, config.player_career_chest_coins_max))
    coins = rng.randint(low, high) if high > 0 else 0
    reward: dict = {"coins": coins, "token": None}
    if coins:
        await wallet_service.credit_coins(
            db, locked, coins, TransactionType.player_career_reward, "Карьера игрока: ежедневный сундук",
            related_object_type="player_career_chest",
        )
    if rng.random() * 100 < config.player_career_chest_token_pct:
        code = await my_player_service._streak_skill(db, mp, today)
        if code:
            row = await _lock_token_row(db, locked.id, code, create=True)
            row.quantity += 1
            reward["token"] = {"code": code, "name": SKILL_DEFINITIONS[code].name, "icon": SKILL_DEFINITIONS[code].icon}
    mp.chest_day = today
    await db.commit()
    reward["balance"] = locked.balance
    return reward


def chest_available(mp: MyPlayer, today: Optional[date] = None) -> bool:
    return mp.chest_day != (today or local_today())


# --- Hall of Fame ----------------------------------------------------------------------------

async def add_club_record(
    db: AsyncSession, user_id: int, club_key: str, club_name: str, matches: int, goals: int, assists: int, title: bool,
) -> None:
    row = (await db.execute(
        select(PlayerCareerClubRecord).where(PlayerCareerClubRecord.user_id == user_id, PlayerCareerClubRecord.club_key == club_key)
    )).scalar_one_or_none()
    if row is None:
        row = PlayerCareerClubRecord(user_id=user_id, club_key=club_key, club_name=club_name[:64], seasons=0, matches=0,
                                     goals=0, assists=0, titles=0)
        db.add(row)
    row.seasons += 1
    row.matches += matches
    row.goals += goals
    row.assists += assists
    row.titles += int(title)


def legend_score(row: PlayerCareerClubRecord) -> int:
    return row.goals * 2 + row.assists + row.titles * 15 + row.seasons * 5


async def hall_of_fame(db: AsyncSession, club_key: str, viewer_id: int, limit: int = 5) -> list[dict]:
    rows = (await db.execute(
        select(PlayerCareerClubRecord, User, MyPlayer).join(User, User.id == PlayerCareerClubRecord.user_id)
        .outerjoin(MyPlayer, MyPlayer.user_id == PlayerCareerClubRecord.user_id)
        .where(PlayerCareerClubRecord.club_key == club_key)
    )).all()
    rows = sorted(rows, key=lambda r: (-legend_score(r[0]), r[0].user_id))[:limit]
    return [
        {"place": i + 1, "user_name": _name(u), "player_name": mp.name if mp else _name(u), "is_me": u.id == viewer_id,
         "seasons": r.seasons, "matches": r.matches, "goals": r.goals, "assists": r.assists, "titles": r.titles}
        for i, (r, u, mp) in enumerate(rows)
    ]


async def top_legends(db: AsyncSession) -> dict[str, dict]:
    """club_key -> its best legend (name, goals) for the club list."""
    rows = (await db.execute(
        select(PlayerCareerClubRecord, MyPlayer).outerjoin(MyPlayer, MyPlayer.user_id == PlayerCareerClubRecord.user_id)
    )).all()
    best: dict[str, tuple[int, dict]] = {}
    for r, mp in rows:
        score = legend_score(r)
        if r.club_key not in best or score > best[r.club_key][0]:
            best[r.club_key] = (score, {"player_name": mp.name if mp else "—", "goals": r.goals, "seasons": r.seasons})
    return {k: v for k, (_, v) in best.items()}


async def count_club_players(db: AsyncSession, club_key: str) -> int:
    return int((await db.execute(
        select(func.count()).select_from(PlayerCareerClubRecord).where(PlayerCareerClubRecord.club_key == club_key)
    )).scalar_one())
