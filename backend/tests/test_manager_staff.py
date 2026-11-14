"""«Менеджер» → «Штаб президента»: the club staff from «Жители города»
(roles, effects within caps, wages at the season start), the VIP «Аналитик»
and «Помощник» for Stars (trial, rules, chores in the window, answers
in the season, the report), skins / cars / rooms, press conferences."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError
from app.models.enums import Position
from app.models.manager_club import ManagerCosmetic, ManagerEvent, ManagerLeague, ManagerStaff
from app.models.town import TownResident, UserTownResident
from app.services import manager_assistant as assistant, manager_finance as finance, manager_perks as perks
from app.services import manager_press as press, manager_service, manager_shop, manager_staff as staff
from app.services.game_config_service import get_config
from tests.factories import create_player
from tests.test_manager import API, _next_season_start, _no_season_at_the_real_clock, _reset_rate_limits  # noqa: F401
from tests.test_manager_finance import _club_row, _keep_loaded, _ledger_sum, _setup, _squad, _user  # noqa: F401

pytestmark = pytest.mark.usefixtures("trade_guards_off")


def _invoice(user_id: int, code: str, stars: int):
    return SimpleNamespace(user_id=user_id, my_player_purchase=f"manager:{code}", stars_amount=stars)


async def _resident(db_session, uid, rarity="rare", name="Доктор Айболит"):
    row = TownResident(name=name, rarity=rarity, is_active=True)
    db_session.add(row)
    await db_session.flush()
    db_session.add(UserTownResident(user_id=uid, resident_id=row.id, copies=1, source="pack"))
    await db_session.commit()
    return row.id


async def test_staff_from_the_town_effects_caps_and_wages(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899701)
    coach = await _resident(db_session, uid, "epic", "Тренер Петрович")
    marketer = await _resident(db_session, uid, "legendary", "Маркетолог Лиза")

    view = (await client.get(f"{API}/manager/staff", headers=headers)).json()
    assert {c["resident_id"] for c in view["candidates"]} == {coach, marketer}
    assert view["slots"] == staff.slots_of((await _club_row(db_session, club_id)).division, config)
    assert {v["code"] for v in view["vip"]} == {"analytics", "assistant"} and all(not v["active"] for v in view["vip"])

    before = await manager_service.wage_bill(db_session, await _club_row(db_session, club_id), config)
    r = await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": coach, "role": "coach"})
    assert r.status_code == 200, r.text
    hired = r.json()["staff"]
    assert len(hired) == 1 and hired[0]["role"] == "coach" and hired[0]["effect"] == staff.effect_of("coach", "epic", config)
    # A role and a resident are taken once.
    assert (await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": marketer, "role": "coach"})).status_code == 409
    assert (await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": coach, "role": "agent"})).status_code == 409
    assert (await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": marketer, "role": "marketing"})).status_code == 200

    club = await _club_row(db_session, club_id)
    wage = staff.wage_of("epic", club.division, config) + staff.wage_of("legendary", club.division, config)
    assert await manager_service.wage_bill(db_session, club, config) == before + wage  # reserved like the squad's wages
    snap = await manager_service.base_snapshot(db_session, uid, config)
    caps = finance.cfg(config)["staff_caps"]
    assert snap["coach_pct"] == min(caps["coach_pct"], staff.effect_of("coach", "epic", config))
    assert snap["matchday_pct"] <= caps["matchday_pct"]
    assert staff.coach_mods({"MID": 1}, {"coach_pct": 2}) == {"GK": 2, "DEF": 2, "MID": 3, "FWD": 2}

    # Wages go out at the season start, into the ledger.
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    assert await _ledger_sum(db_session, club_id, "staff_wages") == -wage
    # Sold the resident → he leaves the staff and stops working.
    row = (await db_session.execute(select(UserTownResident).where(UserTownResident.resident_id == marketer))).scalar_one()
    row.copies = 0
    await db_session.commit()
    assert "marketing" not in await staff.effects(db_session, uid, config)


async def test_fire_frees_the_role(client, db_session, bot_token):
    uid, headers, _club_id = await _setup(client, db_session, bot_token, 899702)
    rid = await _resident(db_session, uid, "common", "Шофёр Гена")
    view = (await client.post(f"{API}/manager/staff/hire", headers=headers, json={"resident_id": rid, "role": "driver"})).json()
    sid = view["staff"][0]["id"]
    assert (await client.post(f"{API}/manager/staff/{sid}/fire", headers=headers)).json()["staff"] == []
    assert (await db_session.execute(select(ManagerStaff))).scalars().all() == []


async def test_vip_bundle_items_and_names(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899703)
    user = await _user(db_session, uid)
    key, _t, _a, price = await manager_shop.stars_order(db_session, uid, staff.BUNDLE, config)
    assert key == f"manager:{staff.BUNDLE}" and price == finance.cfg(config)["staff_bundle_stars"]
    assert (await manager_shop.validate_stars(db_session, _invoice(uid, staff.BUNDLE, price), config))[0]
    await manager_shop.deliver_stars(db_session, user, _invoice(uid, staff.BUNDLE, price), config)
    await db_session.commit()
    club = await _club_row(db_session, club_id)
    assert perks.active(club, "analytics") and perks.active(club, "assistant")

    skins = [i for i in staff.items(config) if i["kind"] == "skin" and i["role"] == "assistant" and i["stars"] > 0]
    skin = skins[0]
    _k, _t, _a, sprice = await manager_shop.stars_order(db_session, uid, skin["code"], config)
    assert sprice == skin["stars"]
    await manager_shop.deliver_stars(db_session, user, _invoice(uid, skin["code"], sprice), config)
    await db_session.commit()
    assert staff.worn(await _club_row(db_session, club_id), config)["assistant"]["code"] == skin["code"]
    with pytest.raises(ConflictError):  # bought once
        await manager_shop.stars_order(db_session, uid, skin["code"], config)

    # A car for coins; a Stars item can't be bought for coins.
    car = next(i for i in staff.items(config) if i["kind"] == "car" and i["coins"] > 0)
    r = await client.post(f"{API}/manager/staff/items/{car['code']}/buy", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["worn"]["car"]["code"] == car["code"]
    assert (await client.post(f"{API}/manager/staff/items/{skins[-1]['code']}/buy", headers=headers)).status_code == 409
    free = next(i for i in staff.items(config) if i["kind"] == "car" and not i["coins"] and not i["stars"])
    assert (await client.post(f"{API}/manager/staff/items/{free['code']}/wear", headers=headers)).json()["worn"]["car"]["code"] == free["code"]
    assert (await db_session.execute(select(ManagerCosmetic).where(ManagerCosmetic.code == car["code"]))).scalar_one()

    r = await client.post(f"{API}/manager/staff/name", headers=headers, json={"role": "assistant", "name": "  Вероника  "})
    assert next(v for v in r.json()["vip"] if v["role"] == "assistant")["name"] == "Вероника"


async def test_assistant_trial_rules_and_window_chores(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899704)
    r = await client.post(f"{API}/manager/assistant/trial", headers=headers)
    assert r.status_code == 200, r.text
    assert next(v for v in r.json()["vip"] if v["role"] == "assistant")["active"]
    assert (await client.post(f"{API}/manager/assistant/trial", headers=headers)).status_code == 409  # once per club

    r = await client.put(f"{API}/manager/assistant/rules", headers=headers, json={"events": "safe", "renew_min_rating": 70})
    assert r.status_code == 200, r.text
    rules = (await client.get(f"{API}/manager/assistant", headers=headers)).json()["rules"]
    assert rules["events"] == "safe" and rules["renew_min_rating"] == 70
    assert (await client.put(f"{API}/manager/assistant/rules", headers=headers, json={"events": "crazy"})).status_code == 422

    start = _next_season_start(config)
    # Not yet: only assistant_hours before the window closes.
    assert await assistant.window_sweep(db_session, start - timedelta(hours=30)) == 0
    near = start - timedelta(minutes=30)
    assert await assistant.window_sweep(db_session, near) == 1
    assert await assistant.window_sweep(db_session, near + timedelta(minutes=5)) == 0  # once a window
    club = await _club_row(db_session, club_id)
    office = (await client.get(f"{API}/manager/assistant", headers=headers)).json()
    texts = " ".join(e["text"] for e in office["report"]["entries"])
    assert "спонсор" in texts.lower()
    assert await finance._taken(db_session, club_id, "sponsor", await finance.upcoming_key(db_session, near))
    assert assistant._spent(club, await finance.upcoming_key(db_session, near)) <= assistant.rules_of(club, config)["limit"]
    assert office["report"]["unseen"] >= 1
    assert (await client.post(f"{API}/manager/assistant/seen", headers=headers)).json()["unseen"] == 0


async def test_assistant_answers_old_events_and_press_with_the_analyst_plan(client, db_session, bot_token):
    config = await get_config(db_session)
    await _squad(db_session, config.manager_division_rating[-1])
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899705)
    club = await _club_row(db_session, club_id)
    perks.extend(club, "assistant", 30)
    perks.extend(club, "analytics", 30)
    await db_session.commit()
    start = _next_season_start(config)
    assert await manager_service.ensure_season(db_session, start)
    league_id = (await _club_row(db_session, club_id)).league_id
    await manager_service.resolve_league(db_session, league_id, now=start + timedelta(days=3))
    league = await db_session.get(ManagerLeague, league_id, populate_existing=True)
    rows = (await db_session.execute(select(ManagerEvent).where(ManagerEvent.club_id == club_id))).scalars().all()
    pressers = [e for e in rows if e.slot >= press.PRESS_SLOT]
    assert pressers, "a press conference after its round"
    for e in rows:
        if int((e.data or {}).get("round", 0)) < league.rounds_played:
            assert e.status != "offered" and e.data.get("by") == "assistant"
    club = await _club_row(db_session, club_id)
    if league.rounds_played < len(league.state["fixtures"]):
        assert club.match_plan is None or club.match_plan.get("round") == league.rounds_played


async def test_analyst_checks_a_deal_and_gives_advice(client, db_session, bot_token):
    config = await get_config(db_session)
    uid, headers, club_id = await _setup(client, db_session, bot_token, 899706)
    target = await create_player(db_session, rating=config.manager_division_rating[-1] + 5, position=Position.ST)
    assert (await client.post(f"{API}/manager/analytics/deal", headers=headers, json={"kind": "npc", "target_id": target.id})).status_code == 403
    club = await _club_row(db_session, club_id)
    perks.extend(club, "analytics", 30)
    await db_session.commit()
    r = await client.post(f"{API}/manager/analytics/deal", headers=headers, json={"kind": "npc", "target_id": target.id})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["verdict"] in ("ok", "meh", "bad") and out["lines"] and out["rating"] == target.rating

    assert perks.advise(70, 75, None)["plan"] == "bus"
    assert perks.advise(80, 70, None)["plan"] == "press"
    assert perks.advise(70, 70, None, my_injuries=2)["plan"] == "rotate"
    with pytest.raises(ForbiddenError):
        await perks.check_deal(db_session, await _user(db_session, (await _setup(client, db_session, bot_token, 899707, name="Барсы"))[0]),
                               "npc", target.id)
