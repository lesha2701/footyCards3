"""«Карьера тренера»: achievements, the trophy cabinet and running streaks
(pure — no DB access). Everything lives in CareerProfile.achievements:

  unlocked   {code: ISO time}
  trophies   [{kind, label, division, season_id, at}]
  run        {wins, unbeaten, clean} — current streaks across seasons
  digest     {week, reputation} — weekly digest bookkeeping (career_service)

career_service calls record_match after every league match of a human and
record_season at the season's end, then credits the coins
(GameConfig.career_achievement_reward) for whatever was newly unlocked.
"""
import copy
from datetime import datetime, timezone
from typing import Optional

ACHIEVEMENTS: list[dict] = [
    {"code": "first_win", "icon": "🥇", "title": "Первая победа", "text": "Выиграй первый матч в карьере"},
    {"code": "win_streak_5", "icon": "🔥", "title": "Серия", "text": "5 побед подряд"},
    {"code": "unbeaten_10", "icon": "🛡", "title": "Без поражений", "text": "10 матчей подряд без поражений"},
    {"code": "clean_sheets_3", "icon": "🧤", "title": "Сухая серия", "text": "3 сухих матча подряд"},
    {"code": "big_win", "icon": "💥", "title": "Разгром", "text": "Победа с разницей 4+ мяча"},
    {"code": "comeback", "icon": "🔄", "title": "Камбэк", "text": "Победа после отставания в счёте"},
    {"code": "tactician", "icon": "🧠", "title": "Тактик",
     "text": "Победа, когда разведка предупреждала о невыгодной тактике"},
    {"code": "objective", "icon": "🎯", "title": "Слово тренера", "text": "Выполни задачу руководства"},
    {"code": "promotion", "icon": "⬆️", "title": "Повышение", "text": "Поднимись в дивизион выше"},
    {"code": "title", "icon": "🏆", "title": "Чемпион", "text": "Выиграй дивизион"},
    {"code": "cup", "icon": "🏅", "title": "Кубок", "text": "Выиграй кубок"},
    {"code": "double", "icon": "✨", "title": "Дубль", "text": "Чемпионство и кубок в одном сезоне"},
    {"code": "unbeaten_season", "icon": "🗿", "title": "Непобедимые", "text": "Сезон без поражений в лиге"},
    {"code": "top_title", "icon": "👑", "title": "Король лиги", "text": "Выиграй высший дивизион"},
    {"code": "veteran", "icon": "🎖", "title": "Ветеран", "text": "Проведи 10 сезонов"},
    {"code": "reputation", "icon": "🌟", "title": "Имя в футболе", "text": "Набери 250 репутации"},
]
BY_CODE = {a["code"]: a for a in ACHIEVEMENTS}
VETERAN_SEASONS = 10
REPUTATION_GOAL = 250


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def data_of(profile) -> dict:
    """A mutable copy of the profile's achievements data (assign it back)."""
    data = copy.deepcopy(profile.achievements or {})
    data.setdefault("unlocked", {})
    data.setdefault("trophies", [])
    data.setdefault("run", {"wins": 0, "unbeaten": 0, "clean": 0})
    return data


def _unlock(data: dict, codes: list[str]) -> list[str]:
    new = [c for c in dict.fromkeys(codes) if c in BY_CODE and c not in data["unlocked"]]
    for code in new:
        data["unlocked"][code] = _now()
    return new


def came_back(events: list[dict], side: str) -> bool:
    """`side` won after trailing at some point (goals in event order)."""
    mine = theirs = 0
    trailed = False
    for e in events or []:
        if e.get("event_type") != "goal":
            continue
        if e.get("team") == side:
            mine += 1
        else:
            theirs += 1
        trailed = trailed or theirs > mine
    return trailed and mine > theirs


def record_match(profile, own: int, opp: int, *, events: Optional[list] = None, side: Optional[str] = None,
                 matchup_hint: Optional[str] = None) -> list[str]:
    """After a league match: streaks and match achievements. Returns the
    newly unlocked codes (profile.achievements is updated)."""
    data = data_of(profile)
    run = data["run"]
    won, lost = own > opp, own < opp
    run["wins"] = run.get("wins", 0) + 1 if won else 0
    run["unbeaten"] = 0 if lost else run.get("unbeaten", 0) + 1
    run["clean"] = run.get("clean", 0) + 1 if opp == 0 else 0
    codes = []
    if won:
        codes.append("first_win")
    if run["wins"] >= 5:
        codes.append("win_streak_5")
    if run["unbeaten"] >= 10:
        codes.append("unbeaten_10")
    if run["clean"] >= 3:
        codes.append("clean_sheets_3")
    if own - opp >= 4:
        codes.append("big_win")
    if won and side and came_back(events or [], side):
        codes.append("comeback")
    if won and matchup_hint == "disadvantage":
        codes.append("tactician")
    new = _unlock(data, codes)
    profile.achievements = data
    return new


def record_season(profile, *, place: int, division: Optional[int], division_label: str, promoted: bool,
                  objective_met: bool, cup_won: bool, unbeaten: bool, season_id: int) -> list[str]:
    """At the season's end: trophies for the cabinet and season
    achievements (profile counters must already be updated)."""
    data = data_of(profile)
    at = _now()
    codes = []
    if place == 1:
        codes.append("title")
        data["trophies"].append({"kind": "title", "label": f"Чемпион: {division_label}", "division": division,
                                 "season_id": season_id, "at": at})
        if division == 1:
            codes.append("top_title")
    if cup_won:
        codes.append("cup")
        data["trophies"].append({"kind": "cup", "label": "Кубок карьеры", "division": division,
                                 "season_id": season_id, "at": at})
    if place == 1 and cup_won:
        codes.append("double")
    if promoted:
        codes.append("promotion")
        data["trophies"].append({"kind": "promotion", "label": f"Повышение из «{division_label}»",
                                 "division": division, "season_id": season_id, "at": at})
    if objective_met:
        codes.append("objective")
    if unbeaten:
        codes.append("unbeaten_season")
    if int(profile.seasons_played or 0) >= VETERAN_SEASONS:
        codes.append("veteran")
    if int(profile.reputation or 0) >= REPUTATION_GOAL:
        codes.append("reputation")
    new = _unlock(data, codes)
    profile.achievements = data
    return new


def achievements_out(profile) -> dict:
    data = data_of(profile)
    unlocked = data["unlocked"]
    return {
        "items": [{**a, "unlocked_at": unlocked.get(a["code"])} for a in ACHIEVEMENTS],
        "unlocked": len([a for a in ACHIEVEMENTS if a["code"] in unlocked]),
        "total": len(ACHIEVEMENTS),
        "trophies": list(reversed(data["trophies"])),
        "run": data["run"],
    }


def titles_text(codes: list[str]) -> str:
    return ", ".join(f"{BY_CODE[c]['icon']} {BY_CODE[c]['title']}" for c in codes if c in BY_CODE)
