"""«Моя вилла» (services/town_villa_service.py): levels and the garage for
coins, things into storage and onto a checked grid, staff of fitting
professions, prestige → rent %, Stars items numbered, guests' likes and
«Вилла недели» paid once."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.town import TownVisit, TownWeekResult, UserTownResident, UserTownVillaItem
from app.services import town_villa_service
from tests.test_town import API, _config, _login, _reset_rate_limits, _resident, _town  # noqa: F401

VILLA = {"villa_price_2": 1000, "garage_price_1": 500, "garage_price_2": 700, "garage_slots_1": 1, "garage_slots_2": 2,
         "coins_palm": 100, "prestige_palm": 6, "coins_car_hatch": 300, "prestige_car_hatch": 30,
         "coins_car_jeep": 300, "prestige_villa_level": 20, "prestige_garage_level": 10, "prestige_staff": 15,
         "prestige_per_pct": 10, "prestige_max_pct": 5, "grid_1": 8, "grid_2": 9}


async def _setup(db_session, **villa):
    await _config(db_session, town_districts={"beach": {"price": 0, "rent": 1000}}, town_price_growth_pct=0,
                  town_villa={**VILLA, **villa})


def test_layout_check_and_settings():
    assert town_villa_service.check_layout(8, [(1, "villa", 1, 1, 0), (2, "pool", 4, 1, 0)]) is None
    assert town_villa_service.check_layout(8, [(1, "villa", 1, 1, 0), (2, "pool", 3, 1, 0)]) == "Клетки уже заняты"
    assert town_villa_service.check_layout(8, [(1, "villa", 6, 1, 0)]) == "Предмет выходит за участок"
    assert town_villa_service.check_layout(8, [(1, "villa", None, None, 0)]) == "Виллу и гараж нельзя убрать на склад"
    # A turned pool (2×3) fits where a straight one (3×2) does not.
    assert town_villa_service.check_layout(8, [(2, "pool", 6, 0, 0)]) is not None
    assert town_villa_service.check_layout(8, [(2, "pool", 6, 0, 1)]) is None
    assert town_villa_service.staff_posts_for("Полицейская") == ["security"]
    assert "garage" in town_villa_service.staff_posts_for("веломеханик из Тронхейма")
    try:
        town_villa_service.validate_villa({"nope": 1})
        raise AssertionError("unknown key accepted")
    except ValueError:
        pass


async def test_villa_levels_items_layout_and_prestige_rent(client, db_session, bot_token):
    await _setup(db_session)
    headers, user = await _login(client, db_session, bot_token, 990401, balance=10_000)
    assert (await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})).status_code == 200

    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    assert state["villa_level"] == 1 and state["grid"] == 8 and state["garage_level"] == 0
    villa = next(i for i in state["items"] if i["code"] == "villa")
    assert (villa["x"], villa["y"], villa["w"]) == (1, 1, 3)
    assert state["prestige"] == 20 and state["prestige_pct"] == 2
    town = (await client.get(f"{API}/town", headers=headers)).json()
    assert town["villa"]["rent_pct"] == 2 and town["villa"]["villa_level"] == 1
    beach = next(d for d in town["districts"] if d["code"] == "beach")
    assert beach["rent"] == 1020  # +2 % from the villa's prestige

    # A car needs the garage first; the garage lands on a free spot.
    hatch = next(s for s in state["shop"] if s["code"] == "car_hatch")
    assert hatch["can_buy"] is False and hatch["reason"] == "Сначала построй гараж"
    assert (await client.post(f"{API}/town/villa/items/car_hatch/buy", headers=headers, json={})).status_code == 409
    up = await client.post(f"{API}/town/villa/upgrade", headers=headers, json={"target": "garage", "idempotency_key": "g1"})
    assert up.status_code == 200, up.text
    assert up.json()["garage_level"] == 1 and up.json()["new_balance"] == 9500
    again = await client.post(f"{API}/town/villa/upgrade", headers=headers, json={"target": "garage", "idempotency_key": "g1"})
    assert again.json()["garage_level"] == 1 and again.json()["new_balance"] == 9500  # replay: no second charge
    garage = next(i for i in up.json()["items"] if i["code"] == "garage")
    assert garage["x"] is not None

    bought = await client.post(f"{API}/town/villa/items/car_hatch/buy", headers=headers, json={})
    assert bought.status_code == 200, bought.text
    assert bought.json()["new_balance"] == 9200 and bought.json()["cars"] == 1
    assert (await client.post(f"{API}/town/villa/items/car_hatch/buy", headers=headers, json={})).status_code == 409  # one each
    assert (await client.post(f"{API}/town/villa/items/car_jeep/buy", headers=headers, json={})).status_code == 409  # garage full
    assert (await client.post(f"{API}/town/villa/items/car_sport/buy", headers=headers, json={})).status_code == 409  # Stars only

    for _ in range(2):  # yard things: as many as fit
        assert (await client.post(f"{API}/town/villa/items/palm/buy", headers=headers, json={})).status_code == 200
    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    palms = [i for i in state["items"] if i["code"] == "palm"]
    assert len(palms) == 2 and all(p["x"] is None for p in palms)  # in storage
    # 20 villa + 10 garage + 30 car + 6 palm (a kind counts once) = 66 → capped at 5 %.
    assert state["prestige"] == 66 and state["prestige_pct"] == 5

    car = next(i for i in state["items"] if i["code"] == "car_hatch")
    bad = await client.put(f"{API}/town/villa/layout", headers=headers,
                           json={"items": [{"id": palms[0]["id"], "x": 1, "y": 1}]})  # onto the villa
    assert bad.status_code == 409
    outside = await client.put(f"{API}/town/villa/layout", headers=headers,
                               json={"items": [{"id": car["id"], "x": 7, "y": 7}]})  # 1×2 off the 8×8 grid
    assert outside.status_code == 409
    ok = await client.put(f"{API}/town/villa/layout", headers=headers, json={"items": [
        {"id": palms[0]["id"], "x": 0, "y": 0}, {"id": palms[1]["id"], "x": 7, "y": 0},
        {"id": car["id"], "x": 6, "y": 6, "rot": 1},
    ]})
    assert ok.status_code == 200, ok.text
    placed = {i["id"]: (i["x"], i["y"], i["rot"]) for i in ok.json()["items"]}
    assert placed[car["id"]] == (6, 6, 1)
    villa_id = next(i["id"] for i in ok.json()["items"] if i["code"] == "villa")
    assert (await client.put(f"{API}/town/villa/layout", headers=headers,
                             json={"items": [{"id": villa_id, "x": None, "y": None}]})).status_code == 409

    chosen = await client.post(f"{API}/town/villa/car", headers=headers, json={"item_id": car["id"]})
    assert chosen.json()["car"]["code"] == "car_hatch"
    assert (await client.post(f"{API}/town/villa/car", headers=headers, json={"item_id": palms[0]["id"]})).status_code == 404

    grown = await client.post(f"{API}/town/villa/upgrade", headers=headers, json={"target": "villa"})
    assert grown.json()["villa_level"] == 2 and grown.json()["grid"] == 9


async def test_staff_takes_fitting_residents_and_adds_prestige(client, db_session, bot_token):
    await _setup(db_session, prestige_per_pct=100)
    headers, user = await _login(client, db_session, bot_token, 990411)
    cop = await _resident(db_session, name="Алина", title="полицейская")
    singer = await _resident(db_session, name="Ливия", title="певица")
    db_session.add_all([UserTownResident(user_id=user.id, resident_id=cop.id, copies=1, source="admin"),
                        UserTownResident(user_id=user.id, resident_id=singer.id, copies=1, source="admin")])
    await db_session.commit()

    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    assert {c["name"]: c["posts"] for c in state["candidates"]} == {"Алина": ["security"], "Ливия": ["party"]}
    wrong = await client.post(f"{API}/town/villa/staff", headers=headers, json={"post": "party", "resident_id": cop.id})
    assert wrong.status_code == 409
    hired = await client.post(f"{API}/town/villa/staff", headers=headers, json={"post": "security", "resident_id": cop.id})
    assert hired.status_code == 200, hired.text
    assert [s["post"] for s in hired.json()["staff"]] == ["security"] and hired.json()["prestige"] == 35
    freed = await client.post(f"{API}/town/villa/staff", headers=headers, json={"post": "security", "resident_id": None})
    assert freed.json()["staff"] == [] and freed.json()["prestige"] == 20


async def test_stars_item_numbered_and_delivered_once(client, db_session, bot_token, monkeypatch):
    from tests.test_town import _fake_invoice_link

    stars_payment_service = await _fake_invoice_link(monkeypatch)
    await _setup(db_session, stars_statue_gold=40, supply_statue_gold=1)
    a_headers, a = await _login(client, db_session, bot_token, 990421)
    b_headers, b = await _login(client, db_session, bot_token, 990422)
    await client.get(f"{API}/town/villa", headers=b_headers)

    inv = await client.post(f"{API}/town/villa/items/statue_gold/invoice", headers=a_headers)
    assert inv.status_code == 200, inv.text
    token = inv.json()["payload_token"]
    assert (await stars_payment_service.validate_pre_checkout(db_session, token, 40))[0]
    await stars_payment_service.deliver_payment(db_session, token, a.telegram_id, "ch-villa-a", 40)
    await stars_payment_service.deliver_payment(db_session, token, a.telegram_id, "ch-villa-a", 40)  # retried
    rows = (await db_session.execute(select(UserTownVillaItem).where(UserTownVillaItem.code == "statue_gold"))).scalars().all()
    assert [(r.user_id, r.serial) for r in rows] == [(a.id, 1)]
    assert (await client.post(f"{API}/town/villa/items/statue_gold/invoice", headers=a_headers)).status_code == 409  # his
    assert (await client.post(f"{API}/town/villa/items/statue_gold/invoice", headers=b_headers)).status_code == 409  # sold out
    status = (await client.get(f"{API}/town/stars-invoices/{token}", headers=a_headers)).json()
    assert status["status"] == "completed"


async def test_guests_like_a_villa_once_a_day_and_villa_week_pays_once(client, db_session, bot_token):
    from app.core.timeutil import local_today

    await _setup(db_session, villa_week_reward_1=700, villa_week_reward_2=300)
    a_headers, a = await _login(client, db_session, bot_token, 990431, balance=0)
    b_headers, b = await _login(client, db_session, bot_token, 990432, balance=0)
    guest_headers, guest = await _login(client, db_session, bot_token, 990433, balance=0)
    guest.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db_session.commit()

    for headers in (a_headers, b_headers):
        assert (await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})).status_code == 200
    no_villa = await client.get(f"{API}/town/visit/{a.id}/villa", headers=guest_headers)
    assert no_villa.status_code == 404 and "виллу" in no_villa.json()["error"]["message"]
    await client.get(f"{API}/town/villa", headers=a_headers)
    await client.get(f"{API}/town/villa", headers=b_headers)
    view = await client.get(f"{API}/town/visit/{a.id}/villa", headers=guest_headers)
    assert view.status_code == 200, view.text
    assert view.json()["villa_level"] == 1 and view.json()["liked"] is False and "shop" not in view.json()
    liked = await client.post(f"{API}/town/visit/{a.id}/villa/like", headers=guest_headers)
    assert liked.status_code == 200 and liked.json()["liked"] is True and liked.json()["likes_total"] == 1
    assert (await client.post(f"{API}/town/visit/{a.id}/villa/like", headers=guest_headers)).status_code == 409
    town_view = (await client.get(f"{API}/town/visit/{a.id}", headers=guest_headers)).json()
    assert town_view["villa"]["villa_level"] == 1

    last_week = local_today() - timedelta(days=7)
    db_session.add_all([
        TownVisit(visitor_id=guest.id, owner_id=b.id, day=last_week, villa_liked=True),
        TownVisit(visitor_id=a.id, owner_id=b.id, day=last_week, villa_liked=True),  # a fresh account: not counted
    ])
    await db_session.commit()
    body = (await client.get(f"{API}/town/villa/week", headers=a_headers)).json()
    assert [(w["user_id"], w["likes"], w["coins"]) for w in body["last_week"]] == [(b.id, 1, 700)]
    assert body["top"][0]["user_id"] == a.id and body["top"][0]["likes"] == 1 and body["me"]["place"] == 1
    await client.get(f"{API}/town/villa/week", headers=b_headers)
    key = town_villa_service.villa_week_key(last_week)
    rows = (await db_session.execute(select(TownWeekResult).where(TownWeekResult.week == key))).scalars().all()
    assert len(rows) == 1
    await db_session.refresh(b)
    assert b.balance == 700
