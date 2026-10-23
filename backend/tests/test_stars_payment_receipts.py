"""Stars payment receipts: every received payment is recorded, failed
deliveries are kept (not lost) and can be retried or refunded."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.core.exceptions import ConflictError
from app.models.notification import Notification
from app.models.pack import PackOpening, StarsInvoice
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.services import stars_payment_service, stars_receipt_service
from tests.test_stars_payments import _fake_invoice_link, _make_stars_pack, _register
from tests.utils import telegram_headers

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
ADMIN_TELEGRAM_ID = 999000001  # in ADMIN_TELEGRAM_IDS (conftest)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _admin_headers(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(ADMIN_TELEGRAM_ID, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def _paid_pack_order(client, db_session, bot_token, monkeypatch, telegram_id, charge_id):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    pack = await _make_stars_pack(db_session, stars_price=5)
    user = await _register(client, db_session, telegram_id, bot_token)
    invoice = (
        await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=telegram_headers(telegram_id, bot_token))
    ).json()
    payload = {
        "payload_token": invoice["payload_token"],
        "telegram_user_id": telegram_id,
        "telegram_payment_charge_id": charge_id,
        "total_amount": 5,
    }
    return pack, user, payload


async def _receipt(db_session, charge_id) -> StarsPaymentReceipt:
    return (
        await db_session.execute(
            select(StarsPaymentReceipt).where(StarsPaymentReceipt.telegram_payment_charge_id == charge_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _openings(db_session, user_id, pack_id) -> int:
    rows = (
        await db_session.execute(
            select(PackOpening).where(PackOpening.user_id == user_id, PackOpening.pack_id == pack_id)
        )
    ).scalars().all()
    return len(rows)


def _deliver(client, payload):
    return client.post("/api/v1/internal/stars-payments/deliver", json=payload, headers=INTERNAL_HEADERS)


async def test_successful_delivery_is_recorded(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870001, "ch-ok")

    assert (await _deliver(client, payload)).status_code == 200

    receipt = await _receipt(db_session, "ch-ok")
    assert receipt.status == "delivered"
    assert receipt.attempts == 1 and receipt.delivered_at is not None and receipt.last_error is None
    assert await _openings(db_session, user.id, pack.id) == 1


async def test_receipt_inserted_by_bot_is_reused(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870002, "ch-bot")
    # The bot writes the receipt itself before calling the backend.
    db_session.add(StarsPaymentReceipt(
        telegram_payment_charge_id="ch-bot", payload_token=payload["payload_token"],
        telegram_user_id=870002, total_amount=5, status="pending", attempts=0,
    ))
    await db_session.commit()

    assert (await _deliver(client, payload)).status_code == 200

    rows = (await db_session.execute(select(StarsPaymentReceipt))).scalars().all()
    assert len(rows) == 1
    assert (await _receipt(db_session, "ch-bot")).status == "delivered"


async def test_failed_delivery_is_kept_and_a_retry_delivers_once(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870003, "ch-retry")

    real_deliver = stars_payment_service.deliver_payment

    async def _broken(*args, **kwargs):
        raise ConflictError("временная ошибка")

    monkeypatch.setattr(stars_payment_service, "deliver_payment", _broken)
    assert (await _deliver(client, payload)).status_code == 409

    receipt = await _receipt(db_session, "ch-retry")
    assert receipt.status == "failed"
    assert receipt.attempts == 1
    assert receipt.last_error == "временная ошибка"
    assert receipt.next_attempt_at is not None
    assert await _openings(db_session, user.id, pack.id) == 0

    monkeypatch.setattr(stars_payment_service, "deliver_payment", real_deliver)
    assert (await _deliver(client, payload)).status_code == 200
    assert (await _deliver(client, payload)).status_code == 200  # a duplicate retry is harmless

    receipt = await _receipt(db_session, "ch-retry")
    assert receipt.status == "delivered" and receipt.attempts == 2
    assert await _openings(db_session, user.id, pack.id) == 1


async def test_pack_switched_off_after_payment_is_still_delivered(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870004, "ch-off")
    # Admin deactivates and re-prices the pack between pre-checkout and the
    # successful_payment update: the player already paid the invoice price.
    pack.is_active = False
    pack.stars_price = 50
    await db_session.commit()

    assert (await _deliver(client, payload)).status_code == 200
    assert await _openings(db_session, user.id, pack.id) == 1


async def test_amount_mismatch_is_still_rejected(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870005, "ch-amount")
    payload["total_amount"] = 1

    assert (await _deliver(client, payload)).status_code == 409
    assert (await _receipt(db_session, "ch-amount")).status == "failed"
    assert await _openings(db_session, user.id, pack.id) == 0


async def test_admin_lists_problems_and_retries(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870006, "ch-admin")
    real_deliver = stars_payment_service.deliver_payment

    async def _broken(*args, **kwargs):
        raise ConflictError("сбой")

    monkeypatch.setattr(stars_payment_service, "deliver_payment", _broken)
    await _deliver(client, payload)
    monkeypatch.setattr(stars_payment_service, "deliver_payment", real_deliver)

    admin = await _admin_headers(client, bot_token)
    listing = (await client.get("/api/v1/admin/stars-purchases/receipts", headers=admin)).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["status"] == "failed" and item["product"] == f"Пак «{pack.name}»" and item["auto_retry"] is True
    assert item["user_id"] == user.id
    count = (await client.get("/api/v1/admin/stars-purchases/receipts/problem-count", headers=admin)).json()
    assert count == {"count": 1}

    resp = await client.post(f"/api/v1/admin/stars-purchases/receipts/{item['id']}/retry", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["status"] == "delivered"
    assert await _openings(db_session, user.id, pack.id) == 1
    notes = (await db_session.execute(select(Notification).where(Notification.user_id == user.id))).scalars().all()
    assert any(n.title == "Покупка начислена" for n in notes)

    again = await client.post(f"/api/v1/admin/stars-purchases/receipts/{item['id']}/retry", headers=admin)
    assert again.status_code == 409
    empty = (await client.get("/api/v1/admin/stars-purchases/receipts", headers=admin)).json()
    assert empty["total"] == 0


async def test_refund_blocks_any_later_delivery(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870007, "ch-refund")
    payload_bad = {**payload, "total_amount": 1}
    await _deliver(client, payload_bad)  # fails → receipt recorded as failed

    refunded: list = []

    async def _fake_refund(telegram_user_id, charge_id):
        refunded.append((telegram_user_id, charge_id))

    monkeypatch.setattr(stars_receipt_service, "_request_telegram_refund", _fake_refund)
    admin = await _admin_headers(client, bot_token)
    receipt = await _receipt(db_session, "ch-refund")

    resp = await client.post(f"/api/v1/admin/stars-purchases/receipts/{receipt.id}/refund", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["status"] == "refunded"
    assert refunded == [(870007, "ch-refund")]
    notes = (await db_session.execute(select(Notification).where(Notification.user_id == user.id))).scalars().all()
    assert any(n.title == "Звёзды возвращены" for n in notes)

    # Neither the bot's retry loop nor an admin can deliver it afterwards.
    assert (await _deliver(client, payload)).status_code == 409
    assert (await client.post(f"/api/v1/admin/stars-purchases/receipts/{receipt.id}/retry", headers=admin)).status_code == 409
    assert await _openings(db_session, user.id, pack.id) == 0
    second = await client.post(f"/api/v1/admin/stars-purchases/receipts/{receipt.id}/refund", headers=admin)
    assert second.status_code == 409
    assert len(refunded) == 1


async def test_delivered_payment_cannot_be_refunded(client, db_session, bot_token, monkeypatch):
    pack, user, payload = await _paid_pack_order(client, db_session, bot_token, monkeypatch, 870008, "ch-done")
    await _deliver(client, payload)

    async def _fake_refund(*args):
        raise AssertionError("must not call Telegram")

    monkeypatch.setattr(stars_receipt_service, "_request_telegram_refund", _fake_refund)
    admin = await _admin_headers(client, bot_token)
    receipt = await _receipt(db_session, "ch-done")
    resp = await client.post(f"/api/v1/admin/stars-purchases/receipts/{receipt.id}/refund", headers=admin)
    assert resp.status_code == 409
    assert (await _receipt(db_session, "ch-done")).status == "delivered"
    invoice = (
        await db_session.execute(select(StarsInvoice).where(StarsInvoice.payload_token == payload["payload_token"]))
    ).scalar_one()
    assert invoice.completed_at is not None


async def test_receipts_require_admin(client, db_session, bot_token):
    await _register(client, db_session, 870009, bot_token)
    resp = await client.get("/api/v1/admin/stars-purchases/receipts", headers=telegram_headers(870009, bot_token))
    assert resp.status_code == 401


def test_retry_backoff_grows_and_is_capped():
    delays = [stars_receipt_service.retry_delay(n).total_seconds() / 60 for n in range(1, 12)]
    assert delays[:4] == [2, 4, 8, 16]
    assert max(delays) == 360
