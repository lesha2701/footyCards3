"""«Установка на матч» and «События клуба»."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError
from app.models.manager_club import ManagerClub, ManagerEvent, ManagerLeague, ManagerLedger
from app.services import manager_events as events, manager_finance as finance, manager_service
from app.services.game_config_service import get_config
from tests.test_manager import API, M, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


def test_plan_and_form_add_to_the_tactics():
    config = type("C", (), {"manager_finance": {}})()
    club = ManagerClub(match_plan={"league_id": 5, "round": 2, "code": "press"},
                       buffs=[{"pct": 3, "league_id": 5, "from": 1, "to": 3}])
    base = {"GK": 0, "DEF": 1, "MID": 2, "FWD": 3}
    assert events.match_mods(base, club, 5, 2, config) == {"GK": 3, "DEF": 4, "MID": 9, "FWD": 10}
    assert events.match_mods(base, club, 5, 3, config) == base  # the plan was for round 2, the form until 3
    assert events.injury_factor(club, 5, 2, config) == 1.5 and events.injury_factor(club, 5, 1, config) == 1
    club.match_plan = {"league_id": 5, "round": 1, "code": "rotate"}
    assert events.injury_factor(club, 5, 1, config) == 0


async def test_plan_for_the_next_match_and_an_event_after_its_round(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899001)
    with pytest.raises(ConflictError):  # no season → no next match
        await events.set_plan(db_session, await _user(db_session, uid), "press")
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    view = await events.set_plan(db_session, await _user(db_session, uid), "rotate")
    assert view["plan"] == "rotate" and view["can_plan"]
    assert {p["code"] for p in view["plans"]} == {"press", "bus", "rotate"}

    league_id = (await _club_row(db_session, club_id)).league_id
    rounds = finance.cfg(config)["event_rounds"]
    # Play to the first event round: the event comes, once.
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(hours=30))
    league = await db_session.get(ManagerLeague, league_id, populate_existing=True)
    assert league.rounds_played >= rounds[0]
    # Rotation spared the first round: nobody was hurt in it.
    hurt = (league.state.get("injuries") or {}).get(str(club_id)) or {}
    assert all(v["back"] - v["rounds"] - 1 != 0 for v in hurt.values())
    opened = (await db_session.execute(select(ManagerEvent).where(ManagerEvent.club_id == club_id))).scalars().all()
    assert [e.slot for e in opened] == [0] if league.rounds_played < rounds[1] else len(opened) >= 1

    event = opened[0]
    view = await events.view(db_session, await _user(db_session, uid))
    assert view["events"][0]["id"] == event.id and len(view["events"][0]["options"]) == 2
    summary = (await client.get(f"{API}/manager/summary", headers=headers)).json()
    assert any(i["code"] == "event" for i in summary["today"])

    option = view["events"][0]["options"][0]
    budget = (await _club_row(db_session, club_id)).budget
    fans = (await _club_row(db_session, club_id)).fans_bonus
    view = await events.choose(db_session, await _user(db_session, uid), event.id, option["code"])
    club = await _club_row(db_session, club_id)
    assert club.budget == budget + option["money"]
    assert club.fans_bonus == max(0, fans + option["fans"])
    if option["form_pct"]:
        assert view["form_pct"] == option["form_pct"]
    assert view["recent"][0]["status"] == "chosen" and not view["events"]
    with pytest.raises(ConflictError):
        await events.choose(db_session, await _user(db_session, uid), event.id, option["code"])
    if option["money"]:
        n = (await db_session.execute(select(func.count(ManagerLedger.id)).where(
            ManagerLedger.club_id == club_id, ManagerLedger.ref == f"event:{event.id}"))).scalar_one()
        assert n == 1
