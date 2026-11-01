"""«Газета лиги»: the last match day of my club's league as a front page —
the headline (my result), the day's results with the biggest win, the
table's top, the top scorer, the transfer of the week and the cup. Built
from the league state on read, nothing stored; shared as a picture
(share kind "manager_news")."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.timeutil import app_timezone, ensure_aware
from app.models.manager_club import ManagerClub, ManagerCup, ManagerLeague, ManagerMove
from app.models.user import User
from app.services.career_service import standings

MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря")


def _day(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    return ensure_aware(datetime.fromisoformat(iso)).astimezone(app_timezone()).date().isoformat()


def _headline(me: str, other: str, mine: int, theirs: int) -> str:
    diff = mine - theirs
    if diff >= 3:
        return f"«{me}» разгромил «{other}» {mine}:{theirs}!"
    if diff > 0:
        return f"«{me}» обыграл «{other}» — {mine}:{theirs}"
    if diff == 0:
        return f"Ничья: «{me}» и «{other}» — {mine}:{theirs}"
    if diff <= -3:
        return f"Провал: «{me}» уступил «{other}» {mine}:{theirs}"
    return f"«{me}» проиграл «{other}» — {mine}:{theirs}"


async def front_page(db: AsyncSession, user: User) -> dict:
    from app.services import manager_service as ms

    club = await ms._owned_club(db, user.id)
    if club is None or not club.league_id:
        raise NotFoundError("Газета выходит, когда клуб играет сезон")
    league = await db.get(ManagerLeague, club.league_id)
    state = (league.state if league else None) or {}
    results = state.get("results") or []
    if not results:
        raise NotFoundError("Первый номер выйдет после первого тура")
    teams = state["teams"]
    schedule = state.get("schedule") or []
    last_day = _day(schedule[len(results) - 1] if len(results) - 1 < len(schedule) else None)
    day_rounds = [r for r in range(len(results)) if _day(schedule[r] if r < len(schedule) else None) == last_day] or [len(results) - 1]
    me = next((t for t in teams if t["club_id"] == club.id), None)

    day_matches = []
    for r in day_rounds:
        for m in results[r]:
            day_matches.append({"round": r + 1, "home": teams[m["home"]]["name"], "away": teams[m["away"]]["name"],
                                "hs": m["hs"], "as": m["as"], "mine": me is not None and me["index"] in (m["home"], m["away"])})
    mine = [m for m in day_matches if m["mine"]]
    headline = "Тур без нашего клуба"
    if mine:
        m = mine[-1]
        home = m["home"] == club.name
        headline = _headline(club.name, m["away"] if home else m["home"], m["hs"] if home else m["as"], m["as"] if home else m["hs"])
    others = [m for m in day_matches if not m["mine"]]
    biggest = max(others or day_matches, key=lambda m: (abs(m["hs"] - m["as"]), m["hs"] + m["as"]))

    table = standings(state)
    top = [{"place": i + 1, "name": teams[row["team_index"]]["name"], "points": row["points"],
            "mine": teams[row["team_index"]]["club_id"] == club.id} for i, row in enumerate(table)]
    my_place = next((r["place"] for r in top if r["mine"]), None)
    scorers = sorted((state.get("players") or {}).values(), key=lambda p: (-p.get("goals", 0), -p.get("assists", 0)))
    scorer = scorers[0] if scorers and scorers[0].get("goals") else None

    move = (await db.execute(
        select(ManagerMove, ManagerClub.name).join(ManagerClub, ManagerClub.id == ManagerMove.club_id)
        .where(ManagerMove.season_key == league.season_key, ManagerMove.direction == "in", ManagerMove.fee > 0)
        .order_by(ManagerMove.fee.desc()).limit(1)
    )).first()
    cup = await db.get(ManagerCup, league.season_key)
    cup_line = None
    if cup is not None:
        names = (cup.state or {}).get("names") or {}
        if cup.status == "finished" and cup.state.get("winner"):
            cup_line = f"Кубок менеджеров выиграл «{names.get(str(cup.state['winner']))}»"
        elif str(club.id) in names:
            from app.services import manager_cup

            played = int(cup.state.get("played", 0))
            out = next((r for r, ms_ in enumerate(cup.state.get("rounds") or []) if any(
                m.get("w") and m["w"] != club.id and club.id in (m["a"], m.get("b")) for m in ms_)), None)
            total = int(cup.state.get("total", 0))
            cup_line = (f"Кубок: «{club.name}» выбыл — {manager_cup.stage_name(total - out)}" if out is not None
                        else f"Кубок: «{club.name}» в игре, впереди {manager_cup.stage_name(total - played) if total > played else 'финал'}")

    date = ensure_aware(datetime.fromisoformat(last_day)) if last_day else None
    return {
        "league": ms.division_name(league.division), "season_key": league.season_key,
        "date": f"{date.day} {MONTHS[date.month - 1]}" if date else None,
        "rounds": [r + 1 for r in day_rounds], "total_rounds": len(state.get("fixtures") or []),
        "headline": headline, "my_place": my_place,
        "biggest": biggest, "matches": day_matches,
        "top": top[:3], "leader": top[0] if top else None,
        "scorer": {"name": scorer["name"], "team": teams[scorer["team_index"]]["name"], "goals": scorer["goals"]} if scorer else None,
        "transfer": {"who": move[0].who, "to": move[1], "from": move[0].other_club, "fee": move[0].fee} if move else None,
        "cup": cup_line,
    }


def lines_of(page: dict, money) -> list[str]:
    """Short lines for the shared picture."""
    out = []
    if page.get("my_place"):
        out.append(f"Наше место в таблице: {page['my_place']}")
    if page.get("leader"):
        out.append(f"Лидер — «{page['leader']['name']}», {page['leader']['points']} очк.")
    b = page.get("biggest")
    if b:
        out.append(f"Крупнейшая победа: {b['home']} {b['hs']}:{b['as']} {b['away']}")
    if page.get("scorer"):
        s = page["scorer"]
        out.append(f"Бомбардир: {s['name']} ({s['team']}) — {s['goals']}")
    if page.get("transfer"):
        t = page["transfer"]
        out.append(f"Трансфер недели: {t['who']} → «{t['to']}», {money(t['fee'])}")
    if page.get("cup"):
        out.append(page["cup"])
    return out
