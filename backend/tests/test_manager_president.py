"""«Кабинет президента», phase 3: the ticket price (attendance, money, the
home crowd, fans), injuries with the season insurance, «Лучший президент»."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.exceptions import ConflictError
from app.models.manager_club import ManagerLeague, ManagerLedger
from app.services import manager_finance as finance, manager_service
from app.services.game_config_service import get_config
from tests.test_manager import API, M, _next_season_start, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


async def _sum(db_session, club_id, kind) -> int:
    return int((await db_session.execute(
        select(func.coalesce(func.sum(ManagerLedger.amount), 0)).where(ManagerLedger.club_id == club_id, ManagerLedger.kind == kind)
    )).scalar_one())


async def _tune(db_session, **values):
    config = await get_config(db_session)
    config.manager_finance = {**(config.manager_finance or {}), **values}
    await db_session.commit()
    return config


def test_ticket_price_trades_attendance_for_money_and_the_crowd():
    class C:
        manager_finance = None

    config = C()
    assert finance.attendance_pct(100, config) == 100 and finance.ticket_factor(100, config) == 100
    assert finance.support_pct(100, config) == 0
    # Dearer: fewer people, a bit more money up to a point, a quieter stadium.
    assert finance.attendance_pct(150, config) == 70
    assert finance.ticket_factor(130, config) > 100 and finance.ticket_factor(200, config) < finance.ticket_factor(130, config)
    assert finance.support_pct(150, config) < 0
    # Cheap: a full stadium pushes the team, the money falls.
    assert finance.support_pct(50, config) > 0 and finance.ticket_factor(50, config) < 100
    assert finance.support_mods({"GK": 1, "DEF": 0, "MID": 0, "FWD": 0}, {"ticket_pct": 50}, config)["GK"] == 1 + finance.support_pct(50, config)


async def test_ticket_price_set_in_the_window_frozen_for_the_season_and_paid(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 897001, {"hq": 4, "stadium": 5})
    resp = await client.post(f"{API}/manager/office/tickets", headers=headers, json={"pct": 201})
    assert resp.status_code == 409
    resp = await client.post(f"{API}/manager/office/tickets", headers=headers, json={"pct": 130})
    assert resp.status_code == 200, resp.text
    assert resp.json()["tickets"]["pct"] == 130
    fans_before = (await _club_row(db_session, club_id)).fans_bonus

    assert await manager_service.ensure_season(db_session, start)
    club = await _club_row(db_session, club_id)
    league = await db_session.get(ManagerLeague, club.league_id)
    team = next(t for t in league.state["teams"] if t["club_id"] == club_id)
    assert team["finance"]["ticket_pct"] == 130
    with pytest.raises(ConflictError):  # the season runs: the price is frozen
        await finance.set_tickets(db_session, await _user(db_session, uid), 90)
    await manager_service.resolve_league(db_session, league.id, now=start + timedelta(days=7))
    league = await db_session.get(ManagerLeague, league.id, populate_existing=True)
    homes = sum(1 for rnd in league.state["fixtures"] for h, _a in rnd if h == team["index"])
    base = manager_service.ticket_income(league.division, team["base"], config)
    assert base > 0
    assert await _sum(db_session, club_id, "tickets") == homes * (base * finance.ticket_factor(130, config) // 100)
    # A dear season loses fans.
    assert (await _club_row(db_session, club_id)).fans_bonus == max(
        0, fans_before + round((finance.attendance_pct(130, config) - 100) * finance.cfg(config)["ticket_fans_per_pct"]))


async def test_injuries_cost_treatment_keep_players_out_and_insurance_pays(client, db_session, bot_token):
    config = await _tune(db_session, injury_chance_pct=100, injury_rounds_min=2, injury_rounds_max=2)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 897011, name="Совы")
    _b_uid, _b_headers, b_id = await _setup(client, db_session, bot_token, 897012, name="Ястребы")
    for club_id in (a_id, b_id):
        club = await _club_row(db_session, club_id)
        club.budget = 50 * M
    await db_session.commit()
    view = (await client.get(f"{API}/manager/office", headers=a_headers)).json()
    premium = view["offers"]["insurance"]["premium"]
    assert premium > 0 and view["offers"]["insurance"]["chance_pct"] == 100
    resp = await client.post(f"{API}/manager/office/deals/insurance", headers=a_headers, json={})
    assert resp.status_code == 200, resp.text
    assert await _sum(db_session, a_id, "insurance") == -premium
    assert (await client.post(f"{API}/manager/office/deals/insurance", headers=a_headers, json={})).status_code == 409

    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, a_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(hours=30))
    league = await db_session.get(ManagerLeague, league_id, populate_existing=True)
    played = league.rounds_played
    assert played >= 2
    for club_id in (a_id, b_id):
        hurt = league.state["injuries"][str(club_id)]
        assert hurt and all(v["rounds"] == 2 for v in hurt.values())
        # Every match hurts one more player; the treatment is paid.
        assert await _sum(db_session, club_id, "injury") == -sum(v["cost"] for v in hurt.values())
    # Insured A gets the treatment back, B pays it.
    assert await _sum(db_session, a_id, "insurance_in") == -await _sum(db_session, a_id, "injury") > 0
    assert await _sum(db_session, b_id, "insurance_in") == 0
    # The injured sit out: a player hurt in round r is not in the XIs of rounds r+1, r+2.
    team = next(t for t in league.state["teams"] if t["club_id"] == a_id)
    last = played - 1  # team["xi"] is the XI of the last round played
    out = {k for k, v in league.state["injuries"][str(a_id)].items() if v["back"] - 1 - v["rounds"] < last < v["back"]}
    assert out and not out & {p.get("key") for p in team["xi"]}
    office = (await client.get(f"{API}/manager/office", headers=a_headers)).json()
    assert office["injuries"] and all(i["rounds_left"] > 0 for i in office["injuries"])


async def test_best_president_rating_by_profit_and_capital(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    start = _next_season_start(config)
    _a_uid, a_headers, a_id = await _setup(client, db_session, bot_token, 897021, name="Совы")
    _b_uid, _b_headers, b_id = await _setup(client, db_session, bot_token, 897022, name="Ястребы")
    rich = await _club_row(db_session, b_id)
    rich.budget = 90 * M
    await db_session.commit()
    resp = await client.get(f"{API}/manager/office/rating", headers=a_headers)
    assert resp.status_code == 200, resp.text
    capital = resp.json()["capital"]
    assert capital["rows"][0]["club_id"] == b_id and capital["rows"][0]["score"] >= 90 * M
    assert capital["my_place"] == 2 and capital["total"] == 2
    assert not capital["rows"][0]["mine"] and capital["rows"][1]["mine"]

    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, a_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(days=7))
    rating = await finance.rating(db_session, await _user(db_session, _a_uid), start + timedelta(days=7))
    assert rating["season_key"] == manager_service.season_key(start)
    profits = {r["club_id"]: r["score"] for r in rating["profit"]["rows"]}
    view = await finance.view(db_session, await _user(db_session, _a_uid), start + timedelta(days=7))
    season = next(s for s in view["report"] if s["key"] == rating["season_key"])
    assert profits[a_id] == season["profit"]
