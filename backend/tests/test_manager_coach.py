"""«Главный тренер» with a character: rolled at the hiring, runs the match
day (formation, style, «Установка на матч», substitutions) unless the
president takes the tactics back, and asks for the player his team lacks."""
import random
from datetime import datetime, timedelta

import pytest

from app.models.manager_club import ManagerLeague
from app.services import manager_coach as coach, manager_service, manager_tactics
from app.services.game_config_service import get_config
from tests.test_manager import API, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _setup, _squad  # noqa: F401
from tests.test_manager_staff import _resident

pytestmark = pytest.mark.usefixtures("trade_guards_off")


def _xi(rating: int = 60, kid_line: str = "") -> list[dict]:
    positions = {"GK": "GK", "DEF": "CB", "MID": "CM", "FWD": "ST"}
    out = []
    for s in manager_service.get_formation_slots("4-3-3"):
        kind = "kid" if s.category == kid_line else "npc"
        out.append({"slot": s.code, "kind": kind, "name": s.code, "position": positions[s.category], "rating": rating})
    return out


def _cat(p):
    return manager_service._category(manager_service.Position(p["position"]))


def test_twelve_characters_and_their_rules():
    assert len(coach.TRAITS) == 12
    assert {"spaniard", "portuguese", "frenchman", "englishman", "german", "italian"} <= set(coach.TRAITS)
    for t in coach.TRAITS.values():
        assert t["formation"] == "fit" or t["formation"] in manager_tactics.FORMATIONS
        assert t["style"] in ("read", *manager_tactics.STYLES)
    assert coach.roll(random.Random(1)) in coach.TRAITS
    # «read»: the style that beats the opponent's.
    assert coach.style_for("portuguese", "possession", "defensive") == "attacking"
    assert coach.style_for("spaniard", "attacking", "defensive") == "possession"
    plans = {"press", "bus", "rotate"}
    assert coach.plan_for("iron", 60, 66, plans)[0] == "bus"
    assert coach.plan_for("iron", 66, 60, plans)[0] == "press"
    assert coach.plan_for("iron", 60, 61, plans)[0] is None
    assert coach.plan_for("englishman", 60, 70, plans)[0] == "press"
    assert coach.plan_for("mentor", 70, 60, plans)[0] == "rotate"
    assert coach.sub_rules("gambler", [60, 70, 80], 3) == ([50, 60, 70], 4)
    assert coach.sub_rules(None, [60, 70, 80], 3) == ([60, 70, 80], 3)
    # «fit»: the formation the squad fills best.
    scores = {"4-4-2": 64, "4-3-3": 62}
    assert coach.formation_for("strategist", [], "4-3-3", ("4-3-3", "4-4-2"), lambda f: scores[f]) == "4-4-2"
    assert coach.formation_for("iron", [], "4-3-3", manager_tactics.FORMATIONS, lambda f: 0) == "4-1-4-1"


def test_the_coach_asks_for_a_kid_line_first_then_his_own():
    ask = coach.request("spaniard", _xi(kid_line="FWD"), _cat)
    assert ask["line"] == "FWD" and "воспитанник" in ask["text"]
    assert coach.request("spaniard", _xi(), _cat)["line"] == "MID"
    xi = _xi()
    for p in xi:
        if p["slot"] == "GK":
            p["rating"] = 50
    assert coach.request("strategist", xi, _cat)["line"] == "GK"  # «weak»: the weakest line


async def test_hired_coach_runs_the_match_day(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 896101)
    rid = await _resident(db_session, uid, "epic", "Тренер Петрович")
    r = await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": rid, "role": "coach"})
    assert r.status_code == 200, r.text
    hired = next(s for s in r.json()["staff"] if s["role"] == "coach")
    assert hired["coach"]["trait"] in coach.TRAITS and hired["coach"]["auto"] is True
    club = await _club_row(db_session, club_id)
    assert club.office["coach"] == {"resident_id": rid, "trait": hired["coach"]["trait"]}
    # Make him «Железный»: 4-1-4-1, defence, a bus against the stronger.
    club.office = {**club.office, "coach": {"resident_id": rid, "trait": "iron"}}
    await db_session.commit()
    view = (await client.get(f"{API}/manager", headers=headers)).json()
    assert view["club"]["coach"]["trait"] == "iron" and view["club"]["coach"]["ask"]["line"] in coach.LINES

    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, club_id)).league_id
    league = await db_session.get(ManagerLeague, league_id)
    first = datetime.fromisoformat(league.state["schedule"][0])
    await manager_service.resolve_league(db_session, league_id, now=first + timedelta(minutes=1))
    league = await db_session.get(ManagerLeague, league_id, populate_existing=True)
    index = next(t["index"] for t in league.state["teams"] if t["club_id"] == club_id)
    game = next(g for g in league.state["results"][0] if index in (g["home"], g["away"]))
    side = 0 if game["home"] == index else 1
    assert game["formations"][side] == "4-1-4-1" and game["styles"][side] == "defensive"
    assert "subs" in game
    club = await _club_row(db_session, club_id)
    assert club.match_plan["by"] == "coach" and club.match_plan["round"] == 1
    assert any("Тренер Петрович" in (e.get("text") or "") for e in (club.office.get("log") or []))

    # The president takes the tactics back: his own formation plays.
    r = await client.patch(f"{API}/manager/club", headers=headers, json={"coach_auto": False, "formation": "4-4-2"})
    assert r.status_code == 200 and r.json()["club"]["coach"]["auto"] is False
    second = datetime.fromisoformat(league.state["schedule"][1])
    await manager_service.resolve_league(db_session, league_id, now=second + timedelta(minutes=1))
    league = await db_session.get(ManagerLeague, league_id, populate_existing=True)
    game = next(g for g in league.state["results"][1] if index in (g["home"], g["away"]))
    assert game["formations"][0 if game["home"] == index else 1] == "4-4-2"

    # Fired: the character goes with him.
    r = await client.post(f"{API}/manager/staff/{hired['id']}/fire", headers=headers)
    assert r.status_code in (200, 409)
    if r.status_code == 200:
        assert "coach" not in ((await _club_row(db_session, club_id)).office or {})
