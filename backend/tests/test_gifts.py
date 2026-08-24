import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.enums import GiftKind, Rarity
from app.models.gift import Gift
from app.services import image_service, stars_payment_service
from tests.factories import create_gift_set, create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/invoice/{payload_token}"


async def _deliver(client, payload_token, telegram_user_id, charge_id, total_amount):
    return await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": payload_token, "telegram_user_id": telegram_user_id,
            "telegram_payment_charge_id": charge_id, "total_amount": total_amount,
        },
        headers=INTERNAL_HEADERS,
    )


async def test_admin_can_create_gift_set_and_send_free_gift(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    recipient_headers = telegram_headers(860001, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860001)

    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Праздничный набор", "description": "test", "coins_amount": 100, "stars_price": 50},
    )
    assert create_resp.status_code == 200
    gift_set_id = create_resp.json()["id"]

    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set_id, "user_id": recipient.id, "message": "С праздником!"},
    )
    assert send_resp.status_code == 200
    assert send_resp.json()["is_admin_gift"] is True
    assert send_resp.json()["message"] == "С праздником!"

    mine_resp = await client.get("/api/v1/gifts/mine", headers=recipient_headers)
    assert mine_resp.status_code == 200
    assert len(mine_resp.json()) == 1
    gift_id = mine_resp.json()[0]["id"]
    assert mine_resp.json()[0]["claimed_at"] is None

    claim_resp = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["coins_credited"] == 100
    assert body["new_balance"] == 500 + 100

    # Claiming twice is rejected.
    second = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
    assert second.status_code == 409


async def test_admin_broadcast_reaches_all_users(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    await _register(client, db_session, 860002, bot_token)
    await _register(client, db_session, 860003, bot_token)
    headers_a = telegram_headers(860002, bot_token)
    headers_b = telegram_headers(860003, bot_token)

    gift_set = await create_gift_set(db_session, name="Всем игрокам", coins_amount=25, stars_price=0)

    broadcast_resp = await client.post(
        "/api/v1/admin/gifts/broadcast", headers=auth,
        json={"gift_set_id": gift_set.id, "message": "Всем игрокам с праздником!"},
    )
    assert broadcast_resp.status_code == 200
    # includes the admin account itself plus both registered players
    assert broadcast_resp.json()["recipients"] >= 3

    for headers in (headers_a, headers_b):
        mine = await client.get("/api/v1/gifts/mine", headers=headers)
        assert len(mine.json()) == 1
        assert mine.json()[0]["message"] == "Всем игрокам с праздником!"


async def test_player_can_buy_gift_for_another_player_with_stars(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await create_player(db_session, rarity=Rarity.epic)
    pack = await create_pack(db_session, "gift-pack", price=0, card_count=1, probabilities={Rarity.epic: 1.0})
    gift_set = await create_gift_set(db_session, name="Дружеский подарок", pack_id=pack.id, coins_amount=30, stars_price=20)

    sender = await _register(client, db_session, 860004, bot_token)
    recipient = await _register(client, db_session, 860005, bot_token)
    sender_headers = telegram_headers(860004, bot_token)
    recipient_headers = telegram_headers(860005, bot_token)

    invoice_resp = await client.post(
        "/api/v1/gifts/invoice", headers=sender_headers,
        json={"gift_set_id": gift_set.id, "recipient_id": recipient.id, "message": "Держи!"},
    )
    assert invoice_resp.status_code == 200
    invoice = invoice_resp.json()
    assert invoice["stars_amount"] == 20

    deliver_resp = await _deliver(client, invoice["payload_token"], 860004, "gift-charge-" + "f" * 120, 20)
    assert deliver_resp.status_code == 200
    assert deliver_resp.json()["gift_result"]["message"] == "Держи!"

    # The sender's own balance/collection are untouched — only the recipient
    # gets anything, and only once they claim it.
    await db_session.refresh(sender)
    assert sender.balance == 500

    mine_resp = await client.get("/api/v1/gifts/mine", headers=recipient_headers)
    assert len(mine_resp.json()) == 1
    gift = mine_resp.json()[0]
    assert gift["sender"]["id"] == sender.id
    assert gift["claimed_at"] is None

    claim_resp = await client.post(f"/api/v1/gifts/{gift['id']}/claim", headers=recipient_headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["coins_credited"] == 30
    assert len(body["pack_result"]["cards"]) == 1
    assert body["new_balance"] == 500 + 30


async def test_cannot_gift_yourself(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    gift_set = await create_gift_set(db_session, stars_price=10)
    user = await _register(client, db_session, 860006, bot_token)
    headers = telegram_headers(860006, bot_token)

    resp = await client.post(
        "/api/v1/gifts/invoice", headers=headers,
        json={"gift_set_id": gift_set.id, "recipient_id": user.id},
    )
    assert resp.status_code == 409


async def test_claiming_someone_elses_gift_404s(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860007, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860007)

    other_headers = telegram_headers(860008, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)

    gift_set = await create_gift_set(db_session, coins_amount=10, stars_price=0)
    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]

    resp = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=other_headers)
    assert resp.status_code == 404


async def test_deleting_gift_set_removes_pending_gifts(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860009, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860009)

    gift_set = await create_gift_set(db_session, name="Temp Set")
    await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )

    delete_resp = await client.delete(f"/api/v1/admin/gifts/sets/{gift_set.id}", headers=auth)
    assert delete_resp.status_code == 204

    remaining = (await db_session.execute(select(Gift).where(Gift.gift_set_id == gift_set.id))).scalars().all()
    assert remaining == []


async def test_buy_collectible_gift_with_coins_for_self(client, db_session, bot_token):
    gift_set = await create_gift_set(
        db_session, name="Золотой кубок", kind=GiftKind.collectible, coins_price=150, stars_price=0, coins_amount=0,
    )
    user = await _register(client, db_session, 860010, bot_token)
    headers = telegram_headers(860010, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_balance"] == 500 - 150
    assert body["gift"]["gift_set"]["kind"] == "collectible"
    assert body["gift"]["claimed_at"] is None

    mine = await client.get("/api/v1/gifts/mine", headers=headers)
    assert len(mine.json()) == 1


async def test_buy_collectible_gift_with_coins_insufficient_balance(client, db_session, bot_token):
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=999999, stars_price=0)
    user = await _register(client, db_session, 860011, bot_token)
    headers = telegram_headers(860011, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 400


async def test_buy_bundle_gift_with_coins_is_rejected(client, db_session, bot_token):
    gift_set = await create_gift_set(db_session, kind=GiftKind.bundle, coins_amount=10, stars_price=20)
    user = await _register(client, db_session, 860012, bot_token)
    headers = telegram_headers(860012, bot_token)

    resp = await client.post(
        f"/api/v1/gifts/collectibles/{gift_set.id}/buy-with-coins", headers=headers,
        json={"recipient_id": user.id},
    )
    assert resp.status_code == 409


async def test_collectible_gift_can_be_sent_to_self_with_stars(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, stars_price=15, coins_price=0)
    user = await _register(client, db_session, 860013, bot_token)
    headers = telegram_headers(860013, bot_token)

    resp = await client.post(
        "/api/v1/gifts/invoice", headers=headers,
        json={"gift_set_id": gift_set.id, "recipient_id": user.id},
    )
    assert resp.status_code == 200


async def test_claiming_collectible_gift_grants_nothing(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860014, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860014)

    gift_set = await create_gift_set(db_session, kind=GiftKind.collectible, coins_price=10, stars_price=0)
    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]

    claim_resp = await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
    assert claim_resp.status_code == 200
    body = claim_resp.json()
    assert body["coins_credited"] == 0
    assert body["pack_result"] is None
    assert body["new_balance"] == 500


async def test_pin_and_unpin_collectible_gift(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860015, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860015)

    gift_ids = []
    for i in range(4):
        gift_set = await create_gift_set(
            db_session, name=f"Кубок {i}", kind=GiftKind.collectible, coins_price=10, stars_price=0,
        )
        send_resp = await client.post(
            "/api/v1/admin/gifts/send", headers=auth,
            json={"gift_set_id": gift_set.id, "user_id": recipient.id},
        )
        gift_id = send_resp.json()["id"]
        await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)
        gift_ids.append(gift_id)

    for gift_id in gift_ids[:3]:
        resp = await client.patch(f"/api/v1/gifts/{gift_id}/pin", headers=recipient_headers, json={"pinned": True})
        assert resp.status_code == 200
        assert resp.json()["is_pinned"] is True

    fourth = await client.patch(f"/api/v1/gifts/{gift_ids[3]}/pin", headers=recipient_headers, json={"pinned": True})
    assert fourth.status_code == 409

    unpin = await client.patch(f"/api/v1/gifts/{gift_ids[0]}/pin", headers=recipient_headers, json={"pinned": False})
    assert unpin.status_code == 200
    assert unpin.json()["is_pinned"] is False

    now_ok = await client.patch(f"/api/v1/gifts/{gift_ids[3]}/pin", headers=recipient_headers, json={"pinned": True})
    assert now_ok.status_code == 200


async def test_pin_bundle_gift_is_rejected(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    recipient_headers = telegram_headers(860016, bot_token)
    await client.post("/api/v1/auth/session", headers=recipient_headers)
    recipient = await get_user_by_telegram_id(db_session, 860016)

    gift_set = await create_gift_set(db_session, kind=GiftKind.bundle, coins_amount=10, stars_price=0)
    send_resp = await client.post(
        "/api/v1/admin/gifts/send", headers=auth,
        json={"gift_set_id": gift_set.id, "user_id": recipient.id},
    )
    gift_id = send_resp.json()["id"]
    await client.post(f"/api/v1/gifts/{gift_id}/claim", headers=recipient_headers)

    resp = await client.patch(f"/api/v1/gifts/{gift_id}/pin", headers=recipient_headers, json={"pinned": True})
    assert resp.status_code == 409


async def test_admin_can_upload_gif_image_for_gift_set(client, bot_token, monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "GIFT_SETS_DIR", tmp_path)
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Анимированный кубок", "kind": "collectible", "coins_price": 100},
    )
    gift_set_id = create_resp.json()["id"]

    gif_bytes = b"GIF89a" + b"\x00" * 20  # minimal fake GIF payload — only the extension/content-type are validated
    upload_resp = await client.post(
        f"/api/v1/admin/gifts/sets/{gift_set_id}/image", headers=auth,
        files={"file": ("cup.gif", gif_bytes, "image/gif")},
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["image_path"].endswith(".gif")


async def test_update_gift_set_cannot_change_kind(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Бандл подарков", "kind": "bundle", "coins_amount": 10, "stars_price": 5},
    )
    assert create_resp.status_code == 200
    gift_set_id = create_resp.json()["id"]
    assert create_resp.json()["kind"] == "bundle"

    update_resp = await client.put(
        f"/api/v1/admin/gifts/sets/{gift_set_id}", headers=auth,
        json={"kind": "collectible", "stars_price": 99},
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["kind"] == "bundle"
    assert body["stars_price"] == 99


async def test_create_collectible_gift_set_requires_a_price(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Бесплатный кубок", "kind": "collectible", "stars_price": 0, "coins_price": 0},
    )
    assert create_resp.status_code == 409


async def test_create_collectible_gift_set_with_only_coins_price_succeeds(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/gifts/sets", headers=auth,
        json={"name": "Кубок за монеты", "kind": "collectible", "coins_price": 50},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["coins_price"] == 50
