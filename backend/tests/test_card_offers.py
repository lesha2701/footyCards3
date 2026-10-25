from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.pack import StarsInvoice
from app.services import card_offer_service, shop_product_service
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
