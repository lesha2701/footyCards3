import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.badge import UserBadge
from app.models.enums import Rarity
from app.models.pack import PackOpening, StarsInvoice
from app.services import stars_payment_service
from tests.factories import create_badge, create_coin_package, create_pack, create_player, get_user_by_telegram_id
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


async def _fake_invoice_link(payload_token, title, description, stars_amount):
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


async def test_create_invoice_converts_telegram_network_error_to_conflict(client, db_session, bot_token, monkeypatch):
    """Observed in production as an unhandled 500 with a raw httpx.ConnectError traceback on
    POST /gifts/invoice — same shape of bug for the pack invoice path, since both funnel
    through _request_telegram_invoice_link. Reproduces it by making the httpx call itself
    raise, rather than monkeypatching the whole helper function like every other test here."""
    import httpx

    class _FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(stars_payment_service.httpx, "AsyncClient", _FailingClient)
    pack = await _make_stars_pack(db_session)
    await _register(client, db_session, 850099, bot_token)
    headers = telegram_headers(850099, bot_token)

    resp = await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)
    assert resp.status_code == 409
    assert "попробуй ещё раз" in resp.json()["error"]["message"]


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
    assert body["status"] == "completed"
    result = body["result"]
    assert len(result["cards"]) == 1
    assert result["cards"][0]["card"]["player"]["rarity"] == "epic"

    status_resp = await client.get(f"/api/v1/packs/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp.json()["status"] == "completed"
    assert status_resp.json()["result"]["opening_id"] == result["opening_id"]

    # Redelivering the same charge (e.g. Telegram redelivers the update)
    # must not grant a second pack.
    second = await client.post("/api/v1/internal/stars-payments/deliver", json=deliver_payload, headers=INTERNAL_HEADERS)
    assert second.status_code == 200
    assert second.json()["result"]["opening_id"] == result["opening_id"]

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


async def test_deliver_payment_grants_bonus_coins_and_badge(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    badge = await create_badge(db_session, name="Supporter", icon="⭐")
    pack = await _make_stars_pack(db_session, stars_price=5)
    pack.bonus_coins = 50
    pack.badge_id = badge.id
    db_session.add(pack)
    await db_session.commit()

    user = await _register(client, db_session, 850013, bot_token)
    headers = telegram_headers(850013, bot_token)
    invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()

    resp = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 850013,
            "telegram_payment_charge_id": "badge-charge-" + "d" * 120,
            "total_amount": 5,
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()["result"]
    assert body["new_balance"] == 500 + 50  # starting balance + bonus_coins (no coin cost, stars-only pack)

    await db_session.refresh(user)
    assert user.balance == 500 + 50
    assert user.active_badge_id == badge.id

    owned = (
        await db_session.execute(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
    ).scalar_one_or_none()
    assert owned is not None

    profile_resp = await client.get("/api/v1/profile/me", headers=headers)
    assert profile_resp.json()["active_badge"]["name"] == "Supporter"


async def test_deliver_payment_regranting_badge_is_idempotent(client, db_session, bot_token, monkeypatch):
    """Buying a second pack that grants the same badge must not violate the
    UserBadge uniqueness constraint or duplicate ownership rows."""
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    badge = await create_badge(db_session, name="Supporter", icon="⭐")
    pack = await _make_stars_pack(db_session, stars_price=5)
    pack.badge_id = badge.id
    db_session.add(pack)
    await db_session.commit()

    user = await _register(client, db_session, 850014, bot_token)
    headers = telegram_headers(850014, bot_token)

    for i in range(2):
        invoice = (await client.post(f"/api/v1/packs/{pack.id}/stars-invoice", headers=headers)).json()
        resp = await client.post(
            "/api/v1/internal/stars-payments/deliver",
            json={
                "payload_token": invoice["payload_token"],
                "telegram_user_id": 850014,
                "telegram_payment_charge_id": f"badge-charge-{i}-" + "e" * 110,
                "total_amount": 5,
            },
            headers=INTERNAL_HEADERS,
        )
        assert resp.status_code == 200

    await db_session.refresh(user)
    assert user.active_badge_id == badge.id

    owned = (
        await db_session.execute(select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge.id))
    ).scalars().all()
    assert len(owned) == 1


# ---------------------------------------------------------------------------
# Buy coins with Stars
# ---------------------------------------------------------------------------

async def test_coin_packages_lists_only_active(client, db_session, bot_token):
    await create_coin_package(db_session, stars_price=10, coins_amount=20, sort_order=0)
    await create_coin_package(db_session, stars_price=50, coins_amount=110, sort_order=1, is_active=False)

    await _register(client, db_session, 850008, bot_token)
    headers = telegram_headers(850008, bot_token)

    resp = await client.get("/api/v1/wallet/coin-packages", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["stars_price"] == 10
    assert body[0]["coins_amount"] == 20


async def test_buy_coins_credits_frozen_package_amount(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    package = await create_coin_package(db_session, stars_price=10, coins_amount=20)

    user = await _register(client, db_session, 850009, bot_token)
    headers = telegram_headers(850009, bot_token)

    invoice = (
        await client.post("/api/v1/wallet/stars-invoice", headers=headers, json={"coin_package_id": package.id})
    ).json()
    assert invoice["stars_amount"] == 10

    resp = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 850009,
            "telegram_payment_charge_id": "coin-charge-" + "b" * 120,
            "total_amount": 10,
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["coin_result"]["coins_credited"] == 20

    await db_session.refresh(user)
    assert user.balance == 500 + 20

    status_resp = await client.get(f"/api/v1/wallet/stars-invoices/{invoice['payload_token']}", headers=headers)
    assert status_resp.json()["coin_result"]["coins_credited"] == 20


async def test_buy_coins_ignores_admin_edit_after_invoice_created(client, db_session, bot_token, monkeypatch):
    """The invoice freezes stars/coins amounts at creation time — an admin
    changing the package afterward must not affect a payment in flight."""
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    package = await create_coin_package(db_session, stars_price=50, coins_amount=110)

    user = await _register(client, db_session, 850010, bot_token)
    headers = telegram_headers(850010, bot_token)

    invoice = (
        await client.post("/api/v1/wallet/stars-invoice", headers=headers, json={"coin_package_id": package.id})
    ).json()

    package.coins_amount = 999
    db_session.add(package)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json={
            "payload_token": invoice["payload_token"],
            "telegram_user_id": 850010,
            "telegram_payment_charge_id": "coin-charge-bulk-" + "c" * 120,
            "total_amount": 50,
        },
        headers=INTERNAL_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["coin_result"]["coins_credited"] == 110

    await db_session.refresh(user)
    assert user.balance == 500 + 110


async def test_buy_coins_rejects_unknown_package(client, db_session, bot_token):
    await _register(client, db_session, 850011, bot_token)
    headers = telegram_headers(850011, bot_token)

    resp = await client.post("/api/v1/wallet/stars-invoice", headers=headers, json={"coin_package_id": 999999})
    assert resp.status_code == 404


async def test_buy_coins_rejects_inactive_package(client, db_session, bot_token):
    package = await create_coin_package(db_session, stars_price=10, coins_amount=20, is_active=False)
    await _register(client, db_session, 850012, bot_token)
    headers = telegram_headers(850012, bot_token)

    resp = await client.post("/api/v1/wallet/stars-invoice", headers=headers, json={"coin_package_id": package.id})
    assert resp.status_code == 404
