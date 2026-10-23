"""Automatic «Матч дня» from API-Football (api-sports.io, key in
settings.api_football_key). The bot calls `sync` every half hour
(/internal/match-day/sync); an admin can call it from «Матч дня».

One pass, at most three requests (the free plan allows 100 a day):
1. results — the bot's matches that kicked off over ~2 hours ago and have no
   score yet, in one request; a finished one gets its 90-minute score (the
   players are notified as with a score entered by hand), a postponed or
   cancelled one is dropped with its guesses;
2. a new match — only while no match is open for guesses, and at most every
   few hours: today's and tomorrow's fixtures, the best league by
   GameConfig.match_day_leagues (earlier = more wanted), then the earliest
   kickoff at least an hour away.

Hand-entered matches are never touched. The outcome of every pass is kept in
GameConfig.match_day_auto_status for the admin page."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.timeutil import app_timezone
from app.models.weekly_event import MatchDayFixture
from app.services import match_day_service
from app.services.game_config_service import get_config

logger = logging.getLogger(__name__)

FINISHED = {"FT", "AET", "PEN"}
DROPPED = {"PST", "CANC", "ABD", "AWD", "WO"}
RESULT_AFTER = timedelta(minutes=115)
MIN_LEAD = timedelta(hours=1)
REFETCH_EVERY = timedelta(hours=6)
MAX_IDS = 20

LEAGUE_NAMES = {
    2: "Лига чемпионов", 3: "Лига Европы", 848: "Лига конференций", 39: "АПЛ", 140: "Ла Лига", 135: "Серия А",
    78: "Бундеслига", 61: "Лига 1", 235: "РПЛ", 1: "Чемпионат мира", 4: "Евро",
}
# API-Football names are English; the clubs players know best get Russian names.
TEAM_NAMES = {
    "Spartak Moscow": "Спартак", "CSKA Moscow": "ЦСКА", "Zenit Saint Petersburg": "Зенит", "Lokomotiv Moscow": "Локомотив",
    "Dynamo Moscow": "Динамо", "FC Krasnodar": "Краснодар", "Krasnodar": "Краснодар", "FK Rostov": "Ростов",
    "Rostov": "Ростов", "Rubin": "Рубин", "Rubin Kazan": "Рубин", "Akhmat Grozny": "Ахмат", "Krylia Sovetov": "Крылья Советов",
    "Fakel Voronezh": "Факел", "Orenburg": "Оренбург", "Nizhny Novgorod": "Пари НН", "Pari NN": "Пари НН",
    "Akron Togliatti": "Акрон", "Dynamo Makhachkala": "Динамо Мх", "Khimki": "Химки", "Baltika": "Балтика", "Sochi": "Сочи",
    "Real Madrid": "Реал Мадрид", "Barcelona": "Барселона", "Atletico Madrid": "Атлетико", "Sevilla": "Севилья",
    "Manchester City": "Манчестер Сити", "Manchester United": "Манчестер Юнайтед", "Liverpool": "Ливерпуль",
    "Arsenal": "Арсенал", "Chelsea": "Челси", "Tottenham": "Тоттенхэм", "Newcastle": "Ньюкасл", "Aston Villa": "Астон Вилла",
    "Bayern München": "Бавария", "Bayern Munich": "Бавария", "Borussia Dortmund": "Боруссия Д", "Bayer Leverkusen": "Байер",
    "RB Leipzig": "РБ Лейпциг", "Paris Saint Germain": "ПСЖ", "Marseille": "Марсель", "Monaco": "Монако",
    "Juventus": "Ювентус", "Inter": "Интер", "AC Milan": "Милан", "Napoli": "Наполи", "AS Roma": "Рома", "Lazio": "Лацио",
    "Atalanta": "Аталанта", "Benfica": "Бенфика", "Porto": "Порту", "Sporting CP": "Спортинг", "Ajax": "Аякс", "PSV Eindhoven": "ПСВ",
    "Galatasaray": "Галатасарай", "Fenerbahce": "Фенербахче", "Celtic": "Селтик",
}

Fetch = Callable[[str, dict], Awaitable[list]]


class ApiError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _http_fetch(path: str, params: dict) -> list:
    settings = get_settings()
    # Three requests at most must fit the bot's 30-second call.
    async with httpx.AsyncClient(timeout=8) as client:
        resp = await client.get(f"{settings.api_football_url}{path}", params=params,
                                headers={"x-apisports-key": settings.api_football_key})
    if resp.status_code != 200:
        raise ApiError(f"HTTP {resp.status_code}")
    body = resp.json()
    errors = body.get("errors")
    if errors:  # a dict ({"plan": "..."}) or a list — API-Football reports quota/plan problems here with HTTP 200
        raise ApiError("; ".join(f"{v}" for v in (errors.values() if isinstance(errors, dict) else errors))[:200])
    return body.get("response") or []


def team_name(name: str) -> str:
    return TEAM_NAMES.get(name, name)[:64]


def _parse_kickoff(item: dict) -> datetime:
    return datetime.fromisoformat(item["fixture"]["date"].replace("Z", "+00:00")).astimezone(timezone.utc)


def _score(item: dict) -> tuple[Optional[int], Optional[int]]:
    """The score after 90 minutes (extra time and penalties don't count for the guesses)."""
    full = (item.get("score") or {}).get("fulltime") or {}
    if full.get("home") is not None and full.get("away") is not None:
        return int(full["home"]), int(full["away"])
    goals = item.get("goals") or {}
    if goals.get("home") is None or goals.get("away") is None:
        return None, None
    return int(goals["home"]), int(goals["away"])


def pick(items: list[dict], leagues: list[int], now: datetime) -> Optional[dict]:
    """The best upcoming fixture: the most wanted league, then the earliest kickoff."""
    rank = {int(lid): i for i, lid in enumerate(leagues)}
    candidates = [
        it for it in items
        if int(it["league"]["id"]) in rank and it["fixture"]["status"]["short"] == "NS"
        and _parse_kickoff(it) >= now + MIN_LEAD
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda it: (rank[int(it["league"]["id"])], _parse_kickoff(it), it["fixture"]["id"]))


async def _results(db: AsyncSession, fetch: Fetch, now: datetime) -> list[str]:
    due = (await db.execute(
        select(MatchDayFixture).where(
            MatchDayFixture.external_id.is_not(None), MatchDayFixture.home_score.is_(None),
            MatchDayFixture.kickoff_at <= now - RESULT_AFTER,
        ).order_by(MatchDayFixture.kickoff_at).limit(MAX_IDS)
    )).scalars().all()
    if not due:
        return []
    items = {int(it["fixture"]["id"]): it for it in await fetch("/fixtures", {"ids": "-".join(str(f.external_id) for f in due)})}
    notes = []
    for f in due:
        item = items.get(f.external_id)
        if item is None:
            continue
        status = item["fixture"]["status"]["short"]
        locked = (await db.execute(
            select(MatchDayFixture).where(MatchDayFixture.id == f.id).with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if locked is None or locked.home_score is not None:
            continue
        if status in FINISHED:
            home, away = _score(item)
            if home is not None:
                await match_day_service.set_result(db, locked, home, away)
                notes.append(f"счёт {locked.home} {home}:{away} {locked.away}")
        elif status in DROPPED:
            notes.append(f"снят {locked.home} — {locked.away} ({status})")
            await match_day_service.drop_fixture(db, locked)
    return notes


async def _new_match(db: AsyncSession, fetch: Fetch, config, now: datetime) -> Optional[str]:
    open_one = (await db.execute(
        select(MatchDayFixture.id).where(MatchDayFixture.kickoff_at > now, MatchDayFixture.home_score.is_(None)).limit(1)
    )).scalar_one_or_none()
    if open_one is not None:
        return None
    checked = config.match_day_auto_checked_at
    if checked is not None and (checked if checked.tzinfo else checked.replace(tzinfo=timezone.utc)) > now - REFETCH_EVERY:
        return None
    today = now.astimezone(app_timezone()).date()
    items: list[dict] = []
    for day in (today, today + timedelta(days=1)):
        items += await fetch("/fixtures", {"date": day.isoformat(), "timezone": "UTC"})
    config.match_day_auto_checked_at = now
    best = pick(items, list(config.match_day_leagues or []), now)
    if best is None:
        return "подходящих матчей на сегодня и завтра нет"
    ext = int(best["fixture"]["id"])
    if (await db.execute(select(MatchDayFixture.id).where(MatchDayFixture.external_id == ext))).scalar_one_or_none():
        return None
    league = LEAGUE_NAMES.get(int(best["league"]["id"]), best["league"].get("name") or "")[:64] or None
    fixture = MatchDayFixture(
        home=team_name(best["teams"]["home"]["name"]), away=team_name(best["teams"]["away"]["name"]),
        league=league, kickoff_at=_parse_kickoff(best), external_id=ext,
    )
    db.add(fixture)
    return f"новый матч {fixture.home} — {fixture.away}"


async def sync(db: AsyncSession, fetch: Optional[Fetch] = None, now: Optional[datetime] = None, force: bool = False) -> dict:
    config = await get_config(db)
    if not (config.match_day_enabled and config.match_day_auto_enabled) and not force:
        return {"status": "выключено"}
    if fetch is None:
        if not get_settings().api_football_key:
            config.match_day_auto_status = "Нет ключа API_FOOTBALL_KEY на сервере"
            await db.commit()
            return {"status": config.match_day_auto_status}
        fetch = _http_fetch
    now = now or _now()
    if force:
        config.match_day_auto_checked_at = None
    try:
        notes = await _results(db, fetch, now)
        new = await _new_match(db, fetch, config, now)
        if new:
            notes.append(new)
        status = "OK" + (": " + "; ".join(notes) if notes else "")
    except (ApiError, httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Match day sync failed: %s", exc)
        await db.rollback()
        config = await get_config(db)
        status = f"Ошибка API-Football: {exc}"
    config.match_day_auto_status = f"{now.astimezone(app_timezone()):%d.%m %H:%M} — {status}"[:255]
    await db.commit()
    return {"status": config.match_day_auto_status}
