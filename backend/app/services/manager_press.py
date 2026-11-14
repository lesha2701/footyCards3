"""«Менеджер» — «Пресс-конференция» and the season forecast.

Press conferences come after `press_rounds` as «События клуба» events (code
"press_…", slot PRESS_SLOT + round) with a question by the club's last
result; the options move fans, money and form like any event
(manager_events.apply_choice), the staff's press attaché adds to the gains.
Numbers: GameConfig.manager_finance over manager_finance.DEFAULTS."""
import random
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manager_club import ManagerClub, ManagerEvent, ManagerLeague
from app.services import manager_finance as finance

PRESS_SLOT = 100


def forecast(league: ManagerLeague, club_id: int) -> Optional[tuple[int, int]]:
    """(place by the squads' ratings, league size)."""
    teams = (league.state or {}).get("teams") or []
    mine = next((t for t in teams if t.get("club_id") == club_id), None)
    if mine is None:
        return None
    ranked = sorted(teams, key=lambda t: (-(t.get("rating") or 0), t["index"]))
    return next(n for n, t in enumerate(ranked, start=1) if t["index"] == mine["index"]), len(teams)


def last_result(league: ManagerLeague, club_id: int) -> Optional[str]:
    state = league.state or {}
    mine = next((t for t in state.get("teams") or [] if t.get("club_id") == club_id), None)
    if mine is None or not state.get("results"):
        return None
    for m in state["results"][-1]:
        for me, f, a in ((m["home"], m["hs"], m["as"]), (m["away"], m["as"], m["hs"])):
            if me == mine["index"]:
                return "win" if f > a else "draw" if f == a else "loss"
    return None


async def after_round(db: AsyncSession, club: ManagerClub, league: ManagerLeague, config) -> None:
    """The (locked) club just played: a press conference may come."""
    cfg = finance.cfg(config)
    if league.rounds_played not in [int(r) for r in cfg["press_rounds"] or []]:
        return
    result = last_result(league, club.id)
    pool = [q for q in cfg["press_questions"] or [] if isinstance(q, dict) and q.get("when") in (result, "any")]
    if not pool:
        return
    q = random.Random(f"press:{league.id}:{club.id}:{league.rounds_played}").choice(sorted(pool, key=lambda x: x["code"]))
    try:
        async with db.begin_nested():
            db.add(ManagerEvent(club_id=club.id, season_key=league.season_key, slot=PRESS_SLOT + league.rounds_played,
                                code=str(q["code"])[:32],
                                data={"title": q.get("title"), "text": q.get("text"), "emoji": q.get("emoji", "🎙"),
                                      "options": q.get("options") or [], "league_id": league.id,
                                      "round": league.rounds_played}))
    except IntegrityError:
        return
