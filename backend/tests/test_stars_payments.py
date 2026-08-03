import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.enums import Rarity
from app.models.pack import PackOpening, StarsInvoice
from app.services import stars_payment_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # The in-memory rate limiter (app/core/rate_limit.py) lives for the whole
    # pytest process, keyed by numeric user id — without this, unrelated
    # tests (including in other files) contend for the same bucket since
    # each test's fresh DB restarts autoincrement ids from 1.
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _fake_invoice_link(payload_token, pack):
    return f"https://t.me/invoice/{payload_token}"


async def _make_stars_pack(db_session, stars_price=1):
    await create_player(db_session, rarity=Rarity.epic)
    return await create_pack(
        db_session, "stars-test", price=0, card_count=1, probabilities={Rarity.epic: 1.0}, stars_price=stars_price,
    )


async def test_create_invoice_requires_stars_price(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.common)
    coin_pack = await create_pack(db_session, "coin-pack", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    await _register(client, db_session, 850001, bot_token)
    headers = telegram_headers(850001, bot_token)

    resp = await client.post(f"/api/v1/packs/{coin_pack.id}/stars-invoice", headers=headers)
    assert resp.status_code == 409


async def test_create_invoice_success(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session)
    await _register(client, db_session, 850002, bot_token)
    headers = telegram_headers(850002, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stars_amount"] == 1
    assert body["payload_token"] in body["invoice_link"]

    status_resp = await client.get(f"/api/v1/packs/stars-invoices/{body['payload_token']}", headers=headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "pending"
    assert status_resp.json()["result"] is None


async def test_coin_purchase_rejected_for_stars_only_pack(client, db_session, bot_token):
    pack = await _make_stars_pack(db_session)
    user = await _register(client, db_session, 850003, bot_token)
    headers = telegram_headers(850003, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 409
    assert user.balance == 500  # nothing was charged


async def test_internal_endpoints_require_secret(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session)
    await _register(client, db_session, 850004, bot_token)
    headers = telegram_headers(850004, bot_token)
    invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()

    no_secret = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 1},
    )
    assert no_secret.status_code == 401

    wrong_secret = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 1},
        headers={"X-Internal-Secret": "wrong"},
    )
    assert wrong_secret.status_code == 401


async def test_pre_checkout_validate(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session, stars_price=5)
    await _register(client, db_session, 850005, bot_token)
    headers = telegram_headers(850005, bot_token)
    invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()

    ok = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 5},
        headers=INTERNAL_HEADERS,
    )
    assert ok.status_code == 200
    assert ok.json()["ok"] is True

    wrong_amount = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": 999},
        headers=INTERNAL_HEADERS,
    )
    assert wrong_amount.json()["ok"] is False

    unknown = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": "does-not-exist", "total_amount": 5},
        headers=INTERNAL_HEADERS,
    )
    assert unknown.json()["ok"] is False


async def test_deliver_payment_grants_pack_and_is_idempotent(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session, stars_price=1)
    user = await _register(client, db_session, 850006, bot_token)
    headers = telegram_headers(850006, bot_token)
    invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()

    deliver_payload = {
        "payload_token": invoice["payload_token"],
        "telegram_user_id": 850006,
        # Real Telegram Stars charge ids observed in production run well past
        # 128 characters (unlike short test fixtures) — this length caused a
        # DB "value too long" 500 on a live payment. Keep this realistically
        # long so a regression here is caught again.
        "telegram_payment_charge_id": "stxhi4w_" + "a" * 120,
        "total_amount": 1,
    }
    resp = await client.post("/api/v1/internal/stars-payments/deliver", json=deliver_payload, headers=INTERNAL_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["cards"]) == 1
    assert body["cards"][0]["card"]["player"]["rarity"] == "epic"

    status_resp = await client.get(f"/api/v1/packs/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp.json()["status"] == "completed"
    assert status_resp.json()["result"]["opening_id"] == body["opening_id"]

    # Redelivering the same charge (e.g. Telegram redelivers the update)
    # must not grant a second pack.
    second = await client.post("/api/v1/internal/stars-payments/deliver", json=deliver_payload, headers=INTERNAL_HEADERS)
    assert second.status_code == 200
    assert second.json()["opening_id"] == body["opening_id"]

    count = (
        await db_session.execute(
            select(PackOpening).where(PackOpening.user_id == user.id, PackOpening.pack_id == pack.id)
        )
    ).scalars().all()
    assert len(count) == 1


async def test_deliver_payment_rejects_amount_mismatch(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session, stars_price=3)
    await _register(client, db_session, 850007, bot_token)
    headers = telegram_headers(850007, bot_token)
    invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()

    resp = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 850007,
            "telegram_payment_charge_id": "charge-xyz",
            "total_amount": 1,  # wrong — pack costs 3
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 409

    invoice_row = (
        await db_session.execute(select(StarsInvoice).where(StarsInvoice.payload_token == invoice["payload_token"]))
    ).scalar_one()
    assert invoice_row.completed_at is None
