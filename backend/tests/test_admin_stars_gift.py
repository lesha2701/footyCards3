"""An admin takes a Stars product free — for himself or as a gift — through
the same pre-checkout and delivery as a real payment; nothing counts as revenue."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import Rarity
from app.models.pack import PackOpening, StarsInvoice
from app.services import stars_payment_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/invoice/{payload_token}"


async def _player(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    session = await client.post("/api/v1/auth/session", headers=headers)
    assert session.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id), headers, session.json().get("admin_token")


async def test_admin_takes_and_gifts_a_stars_pack_for_free(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await create_player(db_session, rarity=Rarity.epic)
    pack = await create_pack(db_session, "stars-gift", price=0, card_count=1, probabilities={Rarity.epic: 1.0}, stars_price=50)
    admin, headers, admin_token = await _player(client, db_session, 999000001, bot_token)  # ADMIN_TELEGRAM_IDS in conftest
    friend, friend_headers, _ = await _player(client, db_session, 7710002, bot_token)
    bearer = {"Authorization": f"Bearer {admin_token}"}

    token = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()["payload_token"]
    r = await client.post(f"/api/v1/admin/stars-purchases/free/{token}", json={}, headers=bearer)
    assert r.status_code == 200 and r.json()["recipient_id"] == admin.id
    status = (await client.get(f"/api/v1/packs/stars-invoices/{token}", headers=headers)).json()
    assert status["status"] == "completed"
    invoice = (await db_session.execute(select(StarsInvoice).where(StarsInvoice.payload_token == token))).scalar_one()
    await db_session.refresh(invoice)
    assert invoice.stars_amount == 0 and invoice.telegram_payment_charge_id == f"admin:{token}"
    # Done once only.
    assert (await client.post(f"/api/v1/admin/stars-purchases/free/{token}", json={}, headers=bearer)).status_code == 409

    token = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()["payload_token"]
    r = await client.post(f"/api/v1/admin/stars-purchases/free/{token}", json={"recipient": str(friend.telegram_id)}, headers=bearer)
    assert r.status_code == 200 and r.json()["recipient_id"] == friend.id
    openings = (await db_session.execute(select(PackOpening).where(PackOpening.user_id == friend.id))).scalars().all()
    assert len(openings) == 1

    # A player can't, and nobody gets someone else's order.
    token = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=friend_headers)).json()["payload_token"]
    assert (await client.post(f"/api/v1/admin/stars-purchases/free/{token}", json={}, headers=friend_headers)).status_code in (401, 403)
    assert (await client.post(f"/api/v1/admin/stars-purchases/free/{token}", json={}, headers=bearer)).status_code == 403
    assert (await client.post(f"/api/v1/admin/stars-purchases/free/nope", json={"recipient": "@nobody"}, headers=bearer)).status_code == 404
