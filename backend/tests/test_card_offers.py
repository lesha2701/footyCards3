from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.core.exceptions import ConflictError
from app.models.card import UserCard
from app.models.card_offer import CardOfferReservation
from app.models.enums import CardSource
from app.models.pack import StarsInvoice
from app.services import card_offer_service, shop_product_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

ADMIN = "/api/v1/admin/card-offers"


async def _admin(client, bot_token):
    rate_limit_module._hits.clear()
    session = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {session.json()['admin_token']}"}


async def _user(client, db_session, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _pay(db_session, user, offer_id, stars, token):
    invoice = StarsInvoice(user_id=user.id, payload_token=token, stars_amount=stars, shop_product=f"card_offer:{offer_id}")
    db_session.add(invoice)
    await db_session.flush()
    ok, reason = await shop_product_service.validate(db_session, invoice)
    return invoice, ok, reason


async def test_admin_sets_up_an_offer_and_players_buy_it_once(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    legend = await create_player(db_session, rating=93, display_name="Old Legend", is_pack_droppable=False)
    await db_session.commit()
    created = await client.post(ADMIN, headers=admin, json={
        "player_id": legend.id, "stars_price": 150, "title": "Переиздание", "stock": 2, "per_user_limit": 1,
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    })
    assert created.status_code == 200, created.text
    offer = created.json()
    assert offer["live"] is True

    headers, user = await _user(client, db_session, bot_token, 990001)
    shop = (await client.get("/api/v1/card-offers", headers=headers)).json()
    assert len(shop) == 1 and shop[0]["retired"] is True and shop[0]["left"] == 2 and shop[0]["can_buy"] is True

    invoice, ok, _ = await _pay(db_session, user, offer["id"], 150, "co-1")
    assert ok
    await shop_product_service.deliver(db_session, user, invoice, "charge-1")
    await shop_product_service.deliver(db_session, user, invoice, "charge-1")  # a redelivery is a no-op
    await db_session.commit()
    owned = (await db_session.execute(
        select(func.count()).select_from(UserCard).where(UserCard.owner_id == user.id, UserCard.player_id == legend.id)
    )).scalar_one()
    assert owned == 1

    # The per-player limit: a second purchase is refused at pre-checkout.
    _, ok, reason = await _pay(db_session, user, offer["id"], 150, "co-2")
    assert not ok and "максимум" in reason
    shop = (await client.get("/api/v1/card-offers", headers=headers)).json()
    assert shop[0]["bought"] == 1 and shop[0]["can_buy"] is False and shop[0]["left"] == 1

    # A changed price, and sold out after the last copy.
    _, other = await _user(client, db_session, bot_token, 990002)
    _, ok, reason = await _pay(db_session, other, offer["id"], 99, "co-3")
    assert not ok and "Цена" in reason
    invoice, ok, _ = await _pay(db_session, other, offer["id"], 150, "co-4")
    assert ok
    await shop_product_service.deliver(db_session, other, invoice, "charge-4")
    await db_session.commit()
    _, third = await _user(client, db_session, bot_token, 990003)
    _, ok, reason = await _pay(db_session, third, offer["id"], 150, "co-5")
    assert not ok and "раскупили" in reason

    # Sold offers can't be deleted, only switched off.
    assert (await client.delete(f"{ADMIN}/{offer['id']}", headers=admin)).status_code == 409


async def test_window_hides_offers_outside_it(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    card = await create_player(db_session, rating=80)
    await db_session.commit()
    now = datetime.now(timezone.utc)
    later = await client.post(ADMIN, headers=admin, json={
        "player_id": card.id, "stars_price": 50, "starts_at": (now + timedelta(days=1)).isoformat(),
    })
    over = await client.post(ADMIN, headers=admin, json={
        "player_id": card.id, "stars_price": 50, "ends_at": (now - timedelta(minutes=1)).isoformat(),
    })
    assert later.json()["live"] is False and over.json()["live"] is False
    headers, user = await _user(client, db_session, bot_token, 990010)
    assert (await client.get("/api/v1/card-offers", headers=headers)).json() == []
    assert (await client.post(f"/api/v1/card-offers/{later.json()['id']}/stars-invoice", headers=headers)).status_code == 409
    bad = await client.post(ADMIN, headers=admin, json={
        "player_id": card.id, "stars_price": 50, "starts_at": now.isoformat(), "ends_at": (now - timedelta(days=1)).isoformat(),
    })
    assert bad.status_code == 409
    # Unsold offers can be deleted.
    assert (await client.delete(f"{ADMIN}/{later.json()['id']}", headers=admin)).status_code == 200
    assert len((await client.get(ADMIN, headers=admin)).json()) == 1
    assert await card_offer_service.list_live(db_session, user) == []


async def test_announce_messages_every_player_once(client, db_session, bot_token):
    from app.models.notification import Notification

    admin = await _admin(client, bot_token)
    _, player_user = await _user(client, db_session, bot_token, 990021)
    legend = await create_player(db_session, rating=91, display_name="Back Again", is_pack_droppable=False)
    await db_session.commit()
    offer = (await client.post(ADMIN, headers=admin, json={"player_id": legend.id, "stars_price": 99, "stock": 5})).json()

    sent = await client.post(f"{ADMIN}/{offer['id']}/announce", headers=admin)
    assert sent.status_code == 200, sent.text
    assert sent.json()["sent"] >= 2  # the admin and the player
    note = (await db_session.execute(
        select(Notification).where(Notification.user_id == player_user.id, Notification.related_object_type == "card_offer")
    )).scalar_one()
    assert "Лимитка" in note.title and "Back Again" in note.body and "99" in note.body

    again = await client.post(f"{ADMIN}/{offer['id']}/announce", headers=admin)
    assert again.status_code == 409
    listed = (await client.get(ADMIN, headers=admin)).json()
    assert listed[0]["announced_at"] is not None


async def test_announce_refuses_an_offer_not_on_sale(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    player = await create_player(db_session, rating=80)
    await db_session.commit()
    offer = (await client.post(ADMIN, headers=admin, json={"player_id": player.id, "stars_price": 50, "is_active": False})).json()
    assert (await client.post(f"{ADMIN}/{offer['id']}/announce", headers=admin)).status_code == 409


async def test_reminder_goes_to_viewers_who_did_not_buy_once(client, db_session, bot_token):
    from app.models.notification import Notification

    admin = await _admin(client, bot_token)
    legend = await create_player(db_session, rating=90, display_name="Last Call", is_pack_droppable=False)
    await db_session.commit()
    ends = datetime.now(timezone.utc) + timedelta(hours=2)
    offer = (await client.post(ADMIN, headers=admin, json={
        "player_id": legend.id, "stars_price": 120, "stock": 10, "ends_at": ends.isoformat(),
    })).json()

    viewer_h, viewer = await _user(client, db_session, bot_token, 990031)
    buyer_h, buyer = await _user(client, db_session, bot_token, 990032)
    _, stranger = await _user(client, db_session, bot_token, 990033)
    for headers in (viewer_h, buyer_h, viewer_h):  # a repeat view is fine
        assert (await client.post("/api/v1/card-offers/seen", headers=headers, json={"ids": [offer["id"], 999999]})).status_code == 200
    invoice, ok, _ = await _pay(db_session, buyer, offer["id"], 120, "rem-1")
    assert ok
    await shop_product_service.deliver(db_session, buyer, invoice, "charge-rem-1")
    await db_session.commit()

    listed = next(o for o in (await client.get(ADMIN, headers=admin)).json() if o["id"] == offer["id"])
    assert (listed["stars_total"], listed["buyers"], listed["viewers"]) == (120, 1, 2)

    assert await card_offer_service.remind_due(db_session) == 1
    assert await card_offer_service.remind_due(db_session) == 0  # once per offer
    reminded = (await db_session.execute(
        select(Notification.user_id).where(Notification.related_object_type == "card_offer")
    )).scalars().all()
    assert reminded == [viewer.id] and stranger.id not in reminded


async def test_no_reminder_while_the_end_is_far(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    card = await create_player(db_session, rating=85)
    await db_session.commit()
    offer = (await client.post(ADMIN, headers=admin, json={
        "player_id": card.id, "stars_price": 80, "ends_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
    })).json()
    headers, _ = await _user(client, db_session, bot_token, 990041)
    await client.post("/api/v1/card-offers/seen", headers=headers, json={"ids": [offer["id"]]})
    assert await card_offer_service.remind_due(db_session) == 0


async def _numbered(client, admin, db_session, stock=2, **player):
    card = await create_player(db_session, rating=91, display_name="Golden", **player)
    await db_session.commit()
    resp = await client.post(ADMIN, headers=admin, json={
        "player_id": card.id, "stars_price": 300, "stock": stock, "per_user_limit": 1, "numbered": True,
    })
    return card, resp


async def test_numbered_edition_gives_each_buyer_a_copy_of_n(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    card, resp = await _numbered(client, admin, db_session)
    assert resp.status_code == 200, resp.text
    offer = resp.json()
    assert offer["numbered"] is True and offer["player"]["edition_size"] == 2
    assert offer["player"]["is_pack_droppable"] is False  # packs never mint a copy

    headers, user = await _user(client, db_session, bot_token, 990030)
    shop = (await client.get("/api/v1/card-offers", headers=headers)).json()
    assert shop[0]["left"] == 2 and shop[0]["player"]["edition_size"] == 2

    invoice, ok, _ = await _pay(db_session, user, offer["id"], 300, "ed-1")
    assert ok
    await shop_product_service.deliver(db_session, user, invoice, "charge-ed-1")
    await db_session.commit()
    copy = (await db_session.execute(select(UserCard).where(UserCard.player_id == card.id))).scalar_one()
    assert copy.serial_number == 1
    assert (await db_session.execute(select(func.count()).select_from(CardOfferReservation))).scalar_one() == 0
    shop = (await client.get("/api/v1/card-offers", headers=headers)).json()
    assert shop[0]["left"] == 1


async def test_two_buyers_cannot_both_pay_for_the_last_copy(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    _, resp = await _numbered(client, admin, db_session, stock=1)
    offer = resp.json()
    _, first = await _user(client, db_session, bot_token, 990031)
    _, second = await _user(client, db_session, bot_token, 990032)

    invoice, ok, _ = await _pay(db_session, first, offer["id"], 300, "last-1")
    assert ok
    _, ok, reason = await _pay(db_session, second, offer["id"], 300, "last-2")
    assert not ok and "оплачивают" in reason

    # The same invoice asking again keeps its copy.
    assert (await shop_product_service.validate(db_session, invoice))[0]

    # An abandoned payment gives the copy back.
    held = (await db_session.execute(select(CardOfferReservation))).scalar_one()
    held.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    _, ok, _ = await _pay(db_session, second, offer["id"], 300, "last-3")
    assert ok


async def test_a_plain_stock_offer_is_held_the_same_way(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    card = await create_player(db_session, rating=85)
    await db_session.commit()
    offer = (await client.post(ADMIN, headers=admin, json={"player_id": card.id, "stars_price": 40, "stock": 1})).json()
    _, first = await _user(client, db_session, bot_token, 990033)
    _, second = await _user(client, db_session, bot_token, 990034)
    assert (await _pay(db_session, first, offer["id"], 40, "plain-1"))[1]
    assert not (await _pay(db_session, second, offer["id"], 40, "plain-2"))[1]


async def test_nothing_but_a_paid_order_passes_the_edition(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    card, resp = await _numbered(client, admin, db_session, stock=1)
    _, user = await _user(client, db_session, bot_token, 990035)
    await db_session.refresh(card)
    card_id, user_id = card.id, user.id
    await create_user_card(db_session, user_id, card_id, CardSource.seed)
    await db_session.commit()
    with pytest.raises(ConflictError):
        await create_user_card(db_session, user_id, card_id, CardSource.seed)
    await db_session.rollback()
    # Already paid: delivered anyway, the shop just stops selling.
    extra = await create_user_card(db_session, user_id, card_id, CardSource.stars_purchase)
    assert extra.serial_number == 2


async def test_edition_rules_for_the_admin(client, db_session, bot_token):
    admin = await _admin(client, bot_token)
    # A card that already has copies can't become numbered: its numbers would lie.
    _, user = await _user(client, db_session, bot_token, 990036)
    old = await create_player(db_session, rating=80)
    await create_user_card(db_session, user.id, old.id, CardSource.seed)
    await db_session.commit()
    body = {"player_id": old.id, "stars_price": 100, "stock": 100, "numbered": True}
    assert (await client.post(ADMIN, headers=admin, json=body)).status_code == 409

    fresh = await create_player(db_session, rating=81)
    await db_session.commit()
    assert (await client.post(ADMIN, headers=admin, json={
        "player_id": fresh.id, "stars_price": 100, "numbered": True,
    })).status_code == 409  # no tirage

    card, resp = await _numbered(client, admin, db_session)
    offer = resp.json()
    invoice, ok, _ = await _pay(db_session, user, offer["id"], 300, "rule-1")
    assert ok
    await shop_product_service.deliver(db_session, user, invoice, "charge-rule-1")
    await db_session.commit()
    change = {"player_id": card.id, "stars_price": 300, "stock": 500, "numbered": True}
    assert (await client.put(f"{ADMIN}/{offer['id']}", headers=admin, json=change)).status_code == 409
    drop = {"player_id": card.id, "stars_price": 300, "stock": 2, "numbered": False}
    assert (await client.put(f"{ADMIN}/{offer['id']}", headers=admin, json=drop)).status_code == 409
