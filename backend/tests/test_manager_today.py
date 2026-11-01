"""«Менеджер» at a glance: the light summary, «Сегодня в клубе» and the
first-season checklist bonus."""
from datetime import timedelta

import pytest

from app.models.enums import Position
from app.services import manager_service
from app.services.game_config_service import get_config
from tests.factories import create_player
from tests.test_manager import API, M, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


async def test_summary_window_checklist_and_bonus_once(client, db_session, bot_token):
    uid, headers, club_id = await _setup(client, db_session, bot_token, 898001)
    resp = await client.get(f"{API}/manager/summary", headers=headers)
    assert resp.status_code == 200, resp.text
    view = resp.json()
    assert view["club"]["name"] == "Совы" and view["season"]["transfers_open"] is True
    codes = [i["code"] for i in view["today"]]
    assert "sponsor" in codes
    steps = {s["code"]: s["done"] for s in view["club"]["checklist"]["steps"]}
    assert steps == {"found": True, "sign": False, "sponsor": False, "deal": False}
    assert (await client.post(f"{API}/manager/onboarding/claim", headers=headers)).status_code == 409

    keeper = await create_player(db_session, rating=60, position=Position.GK, display_name="Новый Вратарь")
    assert (await client.post(f"{API}/manager/npc", headers=headers, json={"player_id": keeper.id, "kind": "loan"})).status_code == 200
    office = (await client.get(f"{API}/manager/office", headers=headers)).json()
    sponsor = office["sponsors"]["offers"][0]["code"]
    assert (await client.post(f"{API}/manager/office/deals/sponsor", headers=headers, json={"option": sponsor})).status_code == 200
    assert (await client.post(f"{API}/manager/office/deals/tv", headers=headers, json={})).status_code == 200

    view = (await client.get(f"{API}/manager/summary", headers=headers)).json()
    assert view["club"]["checklist"]["ready"] is True
    assert "sponsor" not in [i["code"] for i in view["today"]]
    budget = (await _club_row(db_session, club_id)).budget
    resp = await client.post(f"{API}/manager/onboarding/claim", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["club"]["checklist"] is None
    bonus = view["club"]["checklist"]["bonus"]
    assert (await _club_row(db_session, club_id)).budget == budget + bonus
    assert (await client.post(f"{API}/manager/onboarding/claim", headers=headers)).status_code == 409


async def test_summary_shows_the_next_match_and_my_place(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 898002)
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, club_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(hours=30))
    from app.services import manager_today

    view = await manager_today.summary(db_session, await _user(db_session, uid), start + timedelta(hours=30))
    assert view["season"]["phase"] == "season" and view["club"]["trade_locked"] is True
    assert view["league"]["rounds_played"] >= 1 and 1 <= view["league"]["place"] <= view["league"]["size"]
    match = view["club"]["next_match"]
    assert match is not None and match["opponent"]
    assert any(i["code"] in ("match", "edge") for i in view["today"])
    # The mode's view carries only my matches of every round.
    full = await manager_service.get_view(db_session, await _user(db_session, uid), start + timedelta(hours=30))
    assert all(len(r["matches"]) == 1 and r["matches"][0]["mine"] for r in full["league"]["rounds"])
