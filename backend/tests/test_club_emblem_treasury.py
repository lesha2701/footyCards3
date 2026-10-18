"""Club emblem constructor (budget coins / Stars unlocks) and «Казна за Stars»."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.club import Club
from app.models.club_budget import ClubBudgetTransaction
from app.models.club_emblem import ClubDonation, ClubEmblemItem, ClubEmblemUnlock
from app.models.enums import ClubBudgetTransactionType, NotificationType, Position
from app.models.notification import Notification
from app.services import stars_payment_service
from app.services.game_config_service import get_config
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
def _fake_invoice_link(monkeypatch):
    rate_limit_module._hits.clear()

    async def fake_link(payload_token, title, description, stars_amount, subscription_period=None):
        return f"https://t.me/invoice/{payload_token}"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)


@pytest.fixture(autouse=True)
async def _seed_position_pool(db_session):
    # create_club seeds a starting squad — it needs players of every line.
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _club_with_member(client, db_session, bot_token, base_id):
    cap_h, captain = await _register(client, db_session, base_id, bot_token)
    resp = await client.post("/api/v1/clubs", headers=cap_h, json={
        "name": f"Клуб {base_id}", "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })
    assert resp.status_code == 200, resp.text
    club_id = resp.json()["id"]
    mem_h, member = await _register(client, db_session, base_id + 1, bot_token)
    assert (await client.post(f"/api/v1/clubs/{club_id}/join", headers=mem_h)).status_code == 200
    return club_id, cap_h, captain, mem_h, member


async def _item(db_session, kind, style):
    return (await db_session.execute(
        select(ClubEmblemItem).where(ClubEmblemItem.kind == kind, ClubEmblemItem.style_key == style)
    )).scalar_one()


async def _set_budget(db_session, club_id, amount):
    club = await db_session.get(Club, club_id)
    club.budget = amount
    await db_session.commit()


async def _pay(client, token, telegram_id, stars, charge):
    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL,
                            json={"payload_token": token, "total_amount": stars})
    resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL, json={
        "payload_token": token, "telegram_user_id": telegram_id, "telegram_payment_charge_id": charge,
        "total_amount": stars,
    })
    return pre.json(), resp


async def test_catalog_is_seeded_and_nothing_is_unlocked(client, db_session, bot_token):
    _club_id, cap_h, *_ = await _club_with_member(client, db_session, bot_token, 860000)
    body = (await client.get("/api/v1/clubs/me/emblem", headers=cap_h)).json()
    assert body["enabled"] and body["can_edit"] and body["can_spend_budget"]
    kinds = {i["kind"] for i in body["items"]}
    assert kinds == {"color2", "pattern", "letters", "symbol", "outline", "effect"}
    assert not any(i["unlocked"] for i in body["items"])
    assert body["emblem"] == {"color2": None, "pattern": None, "symbol": None, "letters": None,
                              "outline": None, "outline_thin": False, "effect": None}
    # Coins for the cheap layers, Stars for symbols / outlines / effects.
    for item in body["items"]:
        if item["kind"] in ("symbol", "outline", "effect"):
            assert item["stars_price"] > 0 and item["coins_price"] == 0
        else:
            assert item["coins_price"] > 0 and item["stars_price"] == 0


async def test_budget_purchase_unlocks_for_the_club(client, db_session, bot_token):
    club_id, cap_h, _captain, mem_h, _member = await _club_with_member(client, db_session, bot_token, 860010)
    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    checker = await _item(db_session, "pattern", "checker")

    await _set_budget(db_session, club_id, checker.coins_price - 1)
    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{checker.id}/buy", headers=cap_h)
    assert resp.status_code != 200

    # A plain member can't spend the club's budget.
    await _set_budget(db_session, club_id, checker.coins_price + 100)
    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{checker.id}/buy", headers=mem_h)
    assert resp.status_code == 403

    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{checker.id}/buy", headers=cap_h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["budget"] == 100
    assert next(i for i in body["items"] if i["id"] == checker.id)["unlocked"]
    tx = (await db_session.execute(select(ClubBudgetTransaction).where(
        ClubBudgetTransaction.club_id == club_id, ClubBudgetTransaction.type == ClubBudgetTransactionType.emblem_purchase,
    ))).scalar_one()
    assert tx.amount == -checker.coins_price

    again = await client.post(f"/api/v1/clubs/me/emblem/items/{checker.id}/buy", headers=cap_h)
    assert again.status_code == 409

    # Stars items can't be bought for coins.
    crown = await _item(db_session, "symbol", "crown")
    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{crown.id}/buy", headers=cap_h)
    assert resp.status_code == 409


async def test_captain_puts_only_unlocked_layers_on(client, db_session, bot_token):
    club_id, cap_h, _captain, mem_h, _member = await _club_with_member(client, db_session, bot_token, 860020)
    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    base = {"logo_shape": "crest", "logo_color": "#112233"}

    resp = await client.put("/api/v1/clubs/me/emblem", headers=cap_h, json={**base, "pattern": "checker"})
    assert resp.status_code == 409

    # Shape and colour stay free.
    resp = await client.put("/api/v1/clubs/me/emblem", headers=cap_h, json=base)
    assert resp.status_code == 200
    assert resp.json()["logo_shape"] == "crest"

    for kind, style in (("pattern", "checker"), ("color2", "second_color"), ("letters", "letters"),
                        ("symbol", "lion"), ("outline", "gold"), ("effect", "flame")):
        item = await _item(db_session, kind, style)
        db_session.add(ClubEmblemUnlock(club_id=club_id, item_id=item.id, source="admin"))
    await db_session.commit()

    full = {**base, "pattern": "checker", "color2": "#FFFFFF", "letters": "фк", "symbol": "lion",
            "outline": "gold", "outline_thin": True, "effect": "flame"}
    assert (await client.put("/api/v1/clubs/me/emblem", headers=mem_h, json=full)).status_code == 403
    resp = await client.put("/api/v1/clubs/me/emblem", headers=cap_h, json=full)
    assert resp.status_code == 200, resp.text
    assert resp.json()["emblem"] == {"color2": "#FFFFFF", "pattern": "checker", "symbol": "lion", "letters": "ФК",
                                     "outline": "gold", "outline_thin": True, "effect": "flame"}

    bad = await client.put("/api/v1/clubs/me/emblem", headers=cap_h, json={**full, "letters": "a!"})
    assert bad.status_code == 409
    unknown = await client.put("/api/v1/clubs/me/emblem", headers=cap_h, json={**full, "symbol": "dragon"})
    assert unknown.status_code == 409

    # The emblem travels with the club everywhere its logo does.
    listed = (await client.get("/api/v1/clubs", headers=mem_h)).json()
    assert next(c for c in listed if c["id"] == club_id)["emblem"]["symbol"] == "lion"
    assert (await client.get("/api/v1/clubs/me", headers=mem_h)).json()["emblem"]["effect"] == "flame"


async def test_member_buys_a_stars_layer_for_the_club(client, db_session, bot_token):
    club_id, cap_h, _captain, mem_h, member = await _club_with_member(client, db_session, bot_token, 860030)
    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    crown = await _item(db_session, "symbol", "crown")

    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{crown.id}/stars-invoice", headers=mem_h)
    assert resp.status_code == 200, resp.text
    token = resp.json()["payload_token"]
    assert resp.json()["stars_amount"] == crown.stars_price
    pre, delivered = await _pay(client, token, 860031, crown.stars_price, "charge-emblem-1")
    assert pre["ok"] is True
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["shop_result"]["kind"] == "club_emblem"

    unlock = (await db_session.execute(select(ClubEmblemUnlock).where(ClubEmblemUnlock.club_id == club_id))).scalar_one()
    assert (unlock.item_id, unlock.source, unlock.user_id) == (crown.id, "stars", member.id)

    # Redelivery is a no-op; a second purchase is refused.
    _pre, again = await _pay(client, token, 860031, crown.stars_price, "charge-emblem-1")
    assert again.status_code == 200
    assert len((await db_session.execute(select(ClubEmblemUnlock))).scalars().all()) == 1
    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{crown.id}/stars-invoice", headers=cap_h)
    assert resp.status_code == 409


async def test_stars_layer_pre_checkout_refuses_when_already_unlocked(client, db_session, bot_token):
    club_id, cap_h, _captain, mem_h, _member = await _club_with_member(client, db_session, bot_token, 860040)
    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    neon = await _item(db_session, "outline", "neon")
    token = (await client.post(f"/api/v1/clubs/me/emblem/items/{neon.id}/stars-invoice", headers=mem_h)).json()["payload_token"]
    db_session.add(ClubEmblemUnlock(club_id=club_id, item_id=neon.id, source="admin"))
    await db_session.commit()
    pre, _resp = await _pay(client, token, 860041, neon.stars_price, "charge-emblem-2")
    assert pre["ok"] is False


async def _enable_donations(db_session):
    config = await get_config(db_session)
    config.club_donation_enabled = True
    config.club_donation_coins_per_star = 15
    config.club_donation_star_options = [25, 50, 100]
    config.club_sponsor_silver_stars = 75
    config.club_sponsor_gold_stars = 1000
    await db_session.commit()


async def test_donation_is_off_until_launched(client, db_session, bot_token):
    _club_id, _cap_h, _captain, mem_h, _member = await _club_with_member(client, db_session, bot_token, 860050)
    assert (await client.get("/api/v1/clubs/me/treasury", headers=mem_h)).json()["enabled"] is False
    resp = await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 25})
    assert resp.status_code == 409


async def test_donation_tops_up_budget_and_ranks_patrons(client, db_session, bot_token):
    club_id, cap_h, captain, mem_h, member = await _club_with_member(client, db_session, bot_token, 860060)
    await _enable_donations(db_session)
    start_budget = (await db_session.get(Club, club_id)).budget

    assert (await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 30})).status_code == 409

    resp = await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 50})
    assert resp.status_code == 200, resp.text
    token = resp.json()["payload_token"]
    pre, delivered = await _pay(client, token, 860061, 50, "charge-donation-1")
    assert pre["ok"] is True
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["shop_result"] == {"kind": "club_donation", "coins": 750, "club_name": "Клуб 860060"}
    # Redelivery doesn't credit twice.
    await _pay(client, token, 860061, 50, "charge-donation-1")

    await db_session.refresh(await db_session.get(Club, club_id))
    assert (await db_session.get(Club, club_id)).budget == start_budget + 750
    donations = (await db_session.execute(select(ClubDonation))).scalars().all()
    assert [(d.user_id, d.stars, d.coins) for d in donations] == [(member.id, 50, 750)]
    tx = (await db_session.execute(select(ClubBudgetTransaction).where(
        ClubBudgetTransaction.type == ClubBudgetTransactionType.stars_donation,
    ))).scalar_one()
    assert (tx.amount, tx.user_id) == (750, member.id)
    note = (await db_session.execute(select(Notification).where(
        Notification.type == NotificationType.club_donation,
    ))).scalar_one()
    assert note.user_id == captain.id

    token2 = (await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=cap_h, json={"stars": 25})).json()["payload_token"]
    await _pay(client, token2, 860060, 25, "charge-donation-2")
    token3 = (await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 25})).json()["payload_token"]
    await _pay(client, token3, 860061, 25, "charge-donation-3")

    treasury = (await client.get("/api/v1/clubs/me/treasury", headers=mem_h)).json()
    assert treasury["my_stars"] == 75 and treasury["my_tier"] == "silver"
    assert [(p["user_id"], p["stars"], p["coins"], p["tier"]) for p in treasury["patrons"]] == [
        (member.id, 75, 1125, "silver"), (captain.id, 25, 375, "bronze"),
    ]
    assert len(treasury["recent"]) == 3
    members = (await client.get("/api/v1/clubs/me", headers=cap_h)).json()["members"]
    assert {m["user_id"]: m["sponsor_tier"] for m in members} == {captain.id: "bronze", member.id: "silver"}


async def test_donation_pre_checkout_refuses_changed_rate_or_left_club(client, db_session, bot_token):
    _club_id, _cap_h, _captain, mem_h, _member = await _club_with_member(client, db_session, bot_token, 860070)
    await _enable_donations(db_session)
    token = (await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 25})).json()["payload_token"]
    config = await get_config(db_session)
    config.club_donation_coins_per_star = 20
    await db_session.commit()
    pre, _ = await _pay(client, token, 860071, 25, "charge-donation-x")
    assert pre["ok"] is False

    config.club_donation_coins_per_star = 15
    await db_session.commit()
    token = (await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 25})).json()["payload_token"]
    assert (await client.post("/api/v1/clubs/me/leave", headers=mem_h)).status_code == 200
    pre, _ = await _pay(client, token, 860071, 25, "charge-donation-y")
    assert pre["ok"] is False


async def test_admin_edits_emblem_prices(client, db_session, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    admin = {"Authorization": f"Bearer {resp.json()['admin_token']}"}
    items = (await client.get("/api/v1/admin/club-emblem-items", headers=admin)).json()
    lion = next(i for i in items if i["style_key"] == "lion")
    resp = await client.put(f"/api/v1/admin/club-emblem-items/{lion['id']}", headers=admin, json={
        "name": "Лев", "coins_price": 0, "stars_price": 99, "is_active": False, "sort_order": 1,
    })
    assert resp.status_code == 200
    assert resp.json()["stars_price"] == 99 and resp.json()["is_active"] is False
    # Switched-off items disappear from a club that doesn't own them.
    _club_id, cap_h, *_ = await _club_with_member(client, db_session, bot_token, 860080)
    body = (await client.get("/api/v1/clubs/me/emblem", headers=cap_h)).json()
    assert all(i["style_key"] != "lion" for i in body["items"])


async def test_patron_tops_up_club_stars_and_spenders_buy_stars_layers(client, db_session, bot_token):
    from app.models.club_emblem import ClubStarTransaction

    club_id, cap_h, _captain, mem_h, member = await _club_with_member(client, db_session, bot_token, 860090)
    await _enable_donations(db_session)
    await client.get("/api/v1/clubs/me/emblem", headers=cap_h)
    crown_id = (await _item(db_session, "symbol", "crown")).id  # 75 ⭐

    # Not enough on the club balance yet; a plain member can't spend it at all.
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{crown_id}/buy-club-stars", headers=cap_h)).status_code == 409
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{crown_id}/buy-club-stars", headers=mem_h)).status_code == 403

    resp = await client.post("/api/v1/clubs/me/treasury/stars-invoice", headers=mem_h, json={"stars": 100, "target": "stars"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["payload_token"]
    budget = (await db_session.get(Club, club_id)).budget
    pre, delivered = await _pay(client, token, 860091, 100, "charge-club-stars-1")
    assert pre["ok"] is True
    assert delivered.json()["shop_result"] == {"kind": "club_stars", "stars": 100, "club_name": "Клуб 860090"}
    await _pay(client, token, 860091, 100, "charge-club-stars-1")  # redelivery: no double credit

    db_session.expire_all()
    club = await db_session.get(Club, club_id)
    assert club.star_balance == 100 and club.budget == budget
    treasury = (await client.get("/api/v1/clubs/me/treasury", headers=mem_h)).json()
    assert treasury["star_balance"] == 100 and treasury["my_stars"] == 100
    assert treasury["patrons"][0]["coins"] == 0

    resp = await client.post(f"/api/v1/clubs/me/emblem/items/{crown_id}/buy-club-stars", headers=cap_h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["star_balance"] == 25
    assert next(i for i in resp.json()["items"] if i["id"] == crown_id)["unlocked"]
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{crown_id}/buy-club-stars", headers=cap_h)).status_code == 409
    ledger = (await db_session.execute(select(ClubStarTransaction).order_by(ClubStarTransaction.id))).scalars().all()
    assert [(t.amount, t.balance_after, t.kind) for t in ledger] == [(100, 100, "donation"), (-75, 25, "emblem_purchase")]
    # Coin-priced items are never sold for club stars.
    checker = await _item(db_session, "pattern", "checker")
    assert (await client.post(f"/api/v1/clubs/me/emblem/items/{checker.id}/buy-club-stars", headers=cap_h)).status_code == 409
