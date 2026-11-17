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
         "prestige_per_pct": 10, "prestige_max_pct": 5, "cells_1": 60, "cells_2": 90}


def _rect(w, h):
    """A rectangle of cells (the real plot is town_villa_plot.CELLS, the meadow)."""
    return tuple(sorted(((x, y) for x in range(w) for y in range(h)), key=lambda c: (c[0] + c[1], c[0])))


async def _setup(db_session, **villa):
    await _config(db_session, town_districts={"beach": {"price": 0, "rent": 1000}}, town_price_growth_pct=0,
                  town_villa={**VILLA, **villa})


def test_layout_check_and_settings():
    assert town_villa_service.check_layout(_rect(8, 8), [(1, "villa", 1, 1, 0), (2, "pool", 5, 1, 0)]) is None
    assert town_villa_service.check_layout(_rect(8, 8), [(1, "villa", 1, 1, 0), (2, "pool", 4, 1, 0)]) == "Клетки уже заняты"
    assert town_villa_service.check_layout(_rect(8, 8), [(1, "villa", 6, 1, 0)]) == "Предмет выходит за участок"
    assert town_villa_service.check_layout(_rect(8, 8), [(1, "villa", None, None, 0)]) == "Виллу и гараж нельзя убрать на склад"
    # A turned pool (2×3) fits where a straight one (3×2) does not.
    assert town_villa_service.check_layout(_rect(8, 8), [(2, "pool", 6, 0, 0)]) is not None
    assert town_villa_service.check_layout(_rect(8, 8), [(2, "pool", 6, 0, 1)]) is None
    # Any shape: only the given cells are open.
    ring = set(_rect(5, 5)) - {(2, 2)}
    assert town_villa_service.check_layout(ring, [(1, "palm", 2, 2, 0)]) == "Предмет выходит за участок"
    assert town_villa_service.check_layout(ring, [(1, "palm", 0, 0, 0)]) is None
    # A rectangular plot: 9 cells along x, 6 along y.
    assert town_villa_service.check_layout(_rect(9, 6), [(1, "villa", 5, 2, 0)]) is None
    assert town_villa_service.check_layout(_rect(9, 6), [(1, "villa", 3, 4, 0)]) == "Предмет выходит за участок"
    # The meadow plot: the levels open it from the centre outwards and never shrink.
    from app.services.town_villa_plot import CELL_COUNT, CELLS, PLOT_CHECK
    assert len(set(CELLS)) == CELL_COUNT > 300
    assert sum((i + 1) * (x * 64 + y) for i, (x, y) in enumerate(CELLS)) % 1_000_000_007 == PLOT_CHECK  # = lib/villaPlot.ts
    v = town_villa_service.villa_config(type("C", (), {"town_villa": {"cells_2": 1, "cells_5": 10**6}})())
    sizes = [len(town_villa_service.open_cells(v, lvl)) for lvl in range(1, 6)]
    assert sizes == sorted(sizes) and sizes[1] == sizes[0] and sizes[-1] == CELL_COUNT
    assert town_villa_service.staff_posts_for("Полицейская") == ["security"]
    assert "garage" in town_villa_service.staff_posts_for("веломеханик из Тронхейма")
    try:
        town_villa_service.validate_villa({"nope": 1})
        raise AssertionError("unknown key accepted")
    except ValueError:
        pass


def test_layout_repaired_when_the_grid_shrinks():
    from types import SimpleNamespace as Item

    villa = Item(id=1, code="villa", x=5, y=5, rot=0)   # off a 9×6 plot
    palm = Item(id=2, code="palm", x=6, y=0, rot=0)
    far = Item(id=3, code="pool", x=7, y=4, rot=0)      # 3×2 past x = 9
    assert town_villa_service._repair(_rect(9, 6), [villa, palm, far]) is True
    assert (far.x, far.y) == (None, None)               # to storage
    assert (palm.x, palm.y) == (6, 0)                   # stays
    assert (villa.x, villa.y) == (0, 0)                 # moved to the first free spot
    assert town_villa_service.check_layout(_rect(9, 6), [(i.id, i.code, i.x, i.y, i.rot) for i in (villa, palm, far)]) is None
    assert town_villa_service._repair(_rect(9, 6), [villa, palm, far]) is False


def test_combos_and_workplaces():
    from types import SimpleNamespace as Item

    pool = Item(id=1, code="pool", x=2, y=2, rot=0)          # 3×2: cells x 2..4, y 2..3
    palm = Item(id=2, code="palm", x=5, y=4, rot=0)          # touches diagonally
    umbrella = Item(id=3, code="sun_umbrella", x=7, y=7, rot=0)
    kept = Item(id=4, code="sun_umbrella", x=None, y=None, rot=0)
    combos = town_villa_service.combos_of([pool, palm, umbrella, kept])
    assert [(c["a"], c["b"], c["ids"]) for c in combos] == [("pool", "palm", [1, 2])]
    umbrella.x, umbrella.y = 2, 4  # right under the pool
    assert len(town_villa_service.combos_of([pool, palm, umbrella])) == 2
    # The lifeguard works only by a pool on the plot; security always.
    assert town_villa_service.working_posts([pool], ["pool", "security", "kitchen"]) == ["pool", "security"]
    pool.x = pool.y = None
    assert town_villa_service.working_posts([pool], ["pool"]) == []
    # The new things: a pizza oven by the summer kitchen, the patio keeps the lifeguard busy.
    oven = Item(id=5, code="pizza_oven", x=0, y=0, rot=0)
    kitchen = Item(id=6, code="pergola_bbq", x=1, y=0, rot=0)
    patio = Item(id=7, code="patio_pool", x=5, y=0, rot=0)
    assert [c["name"] for c in town_villa_service.combos_of([oven, kitchen, patio])] == ["Итальянский вечер"]
    assert town_villa_service.working_posts([oven, patio], ["kitchen", "pool", "party"]) == ["kitchen", "pool"]
    # Fence sections are 1×1 yard things, as many as fit; a gate is a turned section.
    assert all(town_villa_service.ITEMS[f][2:] == ("yard", 1, 1) for f in town_villa_service.FENCES)
    assert town_villa_service.check_layout(_rect(9, 6), [(1, "fence_iron", 0, 0, 1), (2, "fence_iron", 1, 0, 0)]) is None
    # The farm and the pets: a coop by the vegetable beds, the greenhouse gives the gardener work,
    # the lion is a Stars thing, every new thing has a price and prestige.
    coop = Item(id=8, code="chicken_coop", x=0, y=0, rot=0)
    beds = Item(id=9, code="vegetable_garden", x=2, y=0, rot=0)
    green = Item(id=10, code="greenhouse", x=8, y=8, rot=0)
    assert [c["name"] for c in town_villa_service.combos_of([coop, beds, green])] == ["Своя ферма"]
    assert town_villa_service.working_posts([green], ["garden", "health"]) == ["garden"]
    v = town_villa_service.villa_config(None)
    assert town_villa_service.ITEMS["lion_enclosure"][2:] == ("premium", 3, 3)
    assert town_villa_service.item_price(v, "lion_enclosure") == (0, 500)
    assert town_villa_service.ITEMS["flamingo_pond"][2] == "premium"
    assert town_villa_service.item_price(v, "flamingo_pond") == (0, 300)
    assert town_villa_service.ITEMS["tennis_court"][3:] == (3, 5)
    for code in ("chicken_coop", "staff_house", "dog_kennel", "greenhouse", "vegetable_garden", "stable",
                 "tennis_court", "treehouse", "beehive", "hammock", "basketball_hoop"):
        assert town_villa_service.ITEMS[code][2] == "yard" and town_villa_service.item_price(v, code)[0] > 0
        assert v[f"prestige_{code}"] > 0
    # Every kind of path tile is a 1×1 yard thing for coins and counts as a path in the combos.
    for code in town_villa_service.PATHS:
        assert town_villa_service.ITEMS[code][2:] == ("yard", 1, 1) and town_villa_service.item_price(v, code)[0] > 0
    garage = Item(id=11, code="garage_guest", x=0, y=0, rot=0)
    deck = Item(id=12, code="path_deck", x=2, y=0, rot=0)
    assert [c["name"] for c in town_villa_service.combos_of([garage, deck])] == ["Гостевая парковка"]


async def test_villa_levels_items_layout_and_prestige_rent(client, db_session, bot_token):
    await _setup(db_session)
    headers, user = await _login(client, db_session, bot_token, 990401, balance=10_000)
    assert (await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})).status_code == 200

    from app.services.town_villa_plot import CELL_COUNT, CELLS
    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    assert state["villa_level"] == 1 and state["cells_open"] == 60 and state["garage_level"] == 0
    assert state["cells_total"] == CELL_COUNT and state["combos"] == []
    villa = next(i for i in state["items"] if i["code"] == "villa")
    assert (villa["x"], villa["y"]) == town_villa_service._first_free(CELLS[:60], [], "villa") and villa["w"] == 4
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
                           json={"items": [{"id": palms[0]["id"], "x": villa["x"], "y": villa["y"]}]})  # onto the villa
    assert bad.status_code == 409
    far = CELLS[100]  # a meadow cell level 1 has not opened
    outside = await client.put(f"{API}/town/villa/layout", headers=headers,
                               json={"items": [{"id": car["id"], "x": far[0], "y": far[1]}]})
    assert outside.status_code == 409
    layout = [(i["id"], i["code"], i["x"], i["y"], i["rot"]) for i in state["items"] if i["id"] != car["id"] and i["code"] != "palm"]

    def spot(code, rot):
        for x, y in CELLS[:60]:
            if town_villa_service.check_layout(CELLS[:60], layout + [(0, code, x, y, rot)]) is None:
                layout.append((0, code, x, y, rot))
                return x, y
    (p1x, p1y), (p2x, p2y), (cx, cy) = spot("palm", 0), spot("palm", 0), spot("car_hatch", 1)
    ok = await client.put(f"{API}/town/villa/layout", headers=headers, json={"items": [
        {"id": palms[0]["id"], "x": p1x, "y": p1y}, {"id": palms[1]["id"], "x": p2x, "y": p2y},
        {"id": car["id"], "x": cx, "y": cy, "rot": 1},
    ]})
    assert ok.status_code == 200, ok.text
    placed = {i["id"]: (i["x"], i["y"], i["rot"]) for i in ok.json()["items"]}
    assert placed[car["id"]] == (cx, cy, 1)
    villa_id = next(i["id"] for i in ok.json()["items"] if i["code"] == "villa")
    assert (await client.put(f"{API}/town/villa/layout", headers=headers,
                             json={"items": [{"id": villa_id, "x": None, "y": None}]})).status_code == 409

    chosen = await client.post(f"{API}/town/villa/car", headers=headers, json={"item_id": car["id"]})
    assert chosen.json()["car"]["code"] == "car_hatch"
    assert (await client.post(f"{API}/town/villa/car", headers=headers, json={"item_id": palms[0]["id"]})).status_code == 404

    grown = await client.post(f"{API}/town/villa/upgrade", headers=headers, json={"target": "villa"})
    assert grown.json()["villa_level"] == 2 and grown.json()["cells_open"] == 90


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
    # The singer's party post needs a fire pit or a gazebo on the plot: hired, but not working yet.
    party = await client.post(f"{API}/town/villa/staff", headers=headers, json={"post": "party", "resident_id": singer.id})
    assert party.status_code == 200 and party.json()["prestige"] == 35
    assert {s["post"]: s["working"] for s in party.json()["staff"]} == {"security": True, "party": False}
    freed = await client.post(f"{API}/town/villa/staff", headers=headers, json={"post": "party", "resident_id": None})
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

    await _setup(db_session, villa_week_reward_1=700, villa_week_reward_2=300,
                 month_reward_1=0, month_reward_2=0, month_reward_3=0)
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


def test_perks_count_once_and_only_on_the_plot():
    Item = type("Item", (), {})

    def item(code, x):
        i = Item()
        i.code, i.x, i.y, i.rot = code, x, 0 if x is not None else None, 0
        return i
    # Two pitches are still one training perk; a helipad in storage gives nothing.
    items = [item("pitch_mini", 0), item("pitch_five", 5), item("helipad", None), item("stable", 9)]
    assert town_villa_service.perks_of(items) == ["training", "recovery"]
    v = town_villa_service.villa_config(None)
    assert town_villa_service.income_of(v, 0) == v["income_base"]
    assert town_villa_service.income_of(v, 10**6) == v["income_cap"]


async def _place(db_session, user_id, *codes):
    """Puts things straight onto free cells of the user's plot."""
    from app.services.town_villa_plot import CELLS

    items = list((await db_session.execute(select(UserTownVillaItem).where(UserTownVillaItem.user_id == user_id))).scalars())
    for code in codes:
        spot = town_villa_service._first_free(CELLS, items, code)
        row = UserTownVillaItem(user_id=user_id, code=code, x=spot[0], y=spot[1], rot=0)
        db_session.add(row)
        items.append(row)
    await db_session.commit()


async def test_villa_perks_reach_my_player_and_manager(client, db_session, bot_token):
    from app.core.timeutil import local_today
    from app.models.my_player import MyPlayer
    from app.models.user import User
    from app.services import manager_service, my_player_service
    from app.services.game_config_service import get_config
    from tests.test_my_player import _create

    await _setup(db_session, cells_1=10_000)  # the whole meadow: room for the pitches
    headers, user = await _login(client, db_session, bot_token, 990441)
    assert (await _create(client, headers)).status_code == 200
    await client.get(f"{API}/town/villa", headers=headers)
    config = await get_config(db_session)
    assert await town_villa_service.training_perk(db_session, config, user.id) == 0
    assert (await manager_service.base_snapshot(db_session, user.id, config))["villa_treat_pct"] == 0

    await _place(db_session, user.id, "pitch_mini", "pitch_five", "stable", "helipad")
    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    assert [p["code"] for p in state["perks"]] == ["training", "recovery", "travel"]
    assert {p["code"] for p in state["all_perks"]} == set(town_villa_service.PERKS)
    snap = await manager_service.base_snapshot(db_session, user.id, config)
    v = town_villa_service.villa_config(config)
    assert snap["villa_treat_pct"] == v["perk_treat_pct"] and snap["villa_tour_pct"] == v["perk_tour_pct"]
    from app.services import manager_finance

    plain, cut = manager_finance.tour_terms(3, {}, config), manager_finance.tour_terms(3, snap, config)
    assert cut and all(c["cost"] == p["cost"] * (100 - v["perk_tour_pct"]) // 100 for c, p in zip(cut, plain))

    # Two pitches → one extra free training a day, not two.
    owner = await db_session.get(User, user.id)
    now = datetime.now(timezone.utc)
    for n in range(2):
        await my_player_service.training_start(db_session, owner, now=now + timedelta(minutes=n))
        view = await my_player_service.training_finish(db_session, owner, 1, now=now + timedelta(minutes=n, seconds=10))
    assert view["training"]["villa_perk"] is True and view["training"]["villa_left"] is False
    assert view["training"]["can_train"] is False
    mp = await db_session.get(MyPlayer, user.id)
    assert mp.villa_training_day == local_today() and mp.extra_training_credits == 0
    assert (await client.post(f"{API}/my-player/training/start", headers=headers)).status_code == 409


async def test_villa_income_party_and_month(client, db_session, bot_token, monkeypatch):
    from app.core.timeutil import local_today

    monkeypatch.setattr(town_villa_service, "FIRST_MONTH", "VM0000-00")  # last month counts here

    await _setup(db_session, income_base=50, income_per_100=100, income_cap=60, party_cost=200, party_hours=24,
                 party_guest_coins=25, party_guest_per_day=1, month_reward_1=900, month_like_points=10)
    headers, owner = await _login(client, db_session, bot_token, 990451, balance=1000)
    guest_headers, guest = await _login(client, db_session, bot_token, 990452, balance=0)
    guest.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    await db_session.commit()
    assert (await client.post(f"{API}/town/houses/beach/surf/buy", headers=headers, json={})).status_code == 200
    await client.get(f"{API}/town/villa", headers=headers)

    # Income: 50 + prestige 20 × 100 / 100 = 70 → capped at 60, once a day.
    state = (await client.get(f"{API}/town/villa", headers=headers)).json()
    assert state["income"] == {"coins": 60, "ready": True, "base": 50, "per_100": 100, "cap": 60}
    got = await client.post(f"{API}/town/villa/income", headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["income_paid"] == 60 and got.json()["new_balance"] == 1060 and got.json()["income"]["ready"] is False
    assert (await client.post(f"{API}/town/villa/income", headers=headers)).status_code == 409

    # The party: once a week; a guest's like during it pays the guest.
    party = await client.post(f"{API}/town/villa/party", headers=headers)
    assert party.status_code == 200, party.text
    assert party.json()["new_balance"] == 860 and party.json()["party_until"] and party.json()["party"]["can_throw"] is False
    assert (await client.post(f"{API}/town/villa/party", headers=headers)).status_code == 409
    view = (await client.get(f"{API}/town/visit/{owner.id}/villa", headers=guest_headers)).json()
    assert view["party_guest_coins"] == 25 and view["party_until"]
    liked = (await client.post(f"{API}/town/visit/{owner.id}/villa/like", headers=guest_headers)).json()
    assert liked["party_paid"] == 25 and liked["new_balance"] == 25

    # «Вилла месяца»: last month's ranking pays once.
    last_month = local_today().replace(day=1) - timedelta(days=1)
    db_session.add(TownVisit(visitor_id=guest.id, owner_id=owner.id, day=last_month, villa_liked=True))
    await db_session.commit()
    body = (await client.get(f"{API}/town/villa/week", headers=guest_headers)).json()
    month = body["month"]
    assert [(w["user_id"], w["score"], w["coins"]) for w in month["last_month"]] == [(owner.id, 20 + 10, 900)]
    assert month["top"][0]["user_id"] == owner.id and month["top"][0]["likes"] == 1
    await client.get(f"{API}/town/villa/week", headers=headers)
    rows = (await db_session.execute(select(TownWeekResult).where(
        TownWeekResult.week == town_villa_service.villa_month_key(last_month)))).scalars().all()
    assert len(rows) == 1
    await db_session.refresh(owner)
    assert owner.balance == 860 + 900
