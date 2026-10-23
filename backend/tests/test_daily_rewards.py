"""«Календарь наград»: the monthly login calendar that replaced the 7-day
daily streak (daily_reward_service.py)."""
from datetime import date

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.config import get_settings
from app.models.daily_reward import DailyReward
from app.models.monetization import LoginCalendarBonusClaim, LoginCalendarDay
from app.models.pack import StarsInvoice
from app.services import daily_reward_service, stars_payment_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

TODAY = date(2026, 10, 16)
INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    monkeypatch.setattr(daily_reward_service, "local_today", lambda: TODAY)
    rate_limit_module._hits.clear()
    yield


async def _fake_link(payload_token, title, description, stars_amount, subscription_period=None):
    return f"https://t.me/invoice/{payload_token}"


async def _register(client, db_session, telegram_id, bot_token):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db_session, telegram_id)


async def _admin_auth(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


async def test_calendar_shows_the_whole_month(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, 710001, bot_token)
    body = (await client.get("/api/v1/daily-rewards/calendar", headers=headers)).json()
    assert body["month"] == "2026-10-01"
    assert body["days_in_month"] == 31 and len(body["days"]) == 31
    statuses = {d["day"]: d["status"] for d in body["days"]}
    assert statuses[15] == "missed" and statuses[16] == "today" and statuses[17] == "future"
    # Big days carry more than coins (default template: pack/card on 7/14/21/28).
    assert all(d["is_big"] for d in body["days"] if d["day"] in (7, 14, 21, 28))
    assert body["month_bonus"]["card_rarity"] == "legendary"
    assert body["catchups_left"] == 5


async def test_claim_today_grants_template_reward_once(client, db_session, bot_token):
    headers, _ = await _register(client, db_session, 710002, bot_token)
    expected = 50 + 5 * (TODAY.day - 1)

    first = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert first.status_code == 200
    assert first.json()["day"] == 16
    assert first.json()["granted"]["coins"] == expected
    assert first.json()["new_balance"] == 500 + expected

    second = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert second.status_code == 409

    calendar = (await client.get("/api/v1/daily-rewards/calendar", headers=headers)).json()
    assert calendar["already_claimed_today"] is True
    assert next(d for d in calendar["days"] if d["day"] == 16)["status"] == "claimed"


async def test_big_day_grants_card(client, db_session, bot_token, monkeypatch):
    await create_player(db_session)
    from app.models.enums import Rarity

    await create_player(db_session, rarity=Rarity.rare)
    monkeypatch.setattr(daily_reward_service, "local_today", lambda: date(2026, 10, 14))
    headers, _ = await _register(client, db_session, 710003, bot_token)
    body = (await client.post("/api/v1/daily-rewards/claim", headers=headers)).json()
    assert len(body["granted"]["cards"]) == 1
    assert body["granted"]["cards"][0]["player"]["rarity"] == "rare"


async def test_missed_day_can_be_caught_up_for_coins(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 710004, bot_token)
    resp = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-03"})
    assert resp.status_code == 200
    reward = 50 + 5 * 2
    assert resp.json()["new_balance"] == 500 - 150 + reward

    row = (await db_session.execute(select(DailyReward).where(
        DailyReward.user_id == user.id, DailyReward.reward_date == date(2026, 10, 3),
    ))).scalar_one()
    assert row.claim_method == "coins"

    again = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-03"})
    assert again.status_code == 409


@pytest.mark.parametrize("day", ["2026-10-16", "2026-10-20", "2026-09-30"])
async def test_catch_up_only_for_past_days_of_this_month(client, db_session, bot_token, day):
    headers, _ = await _register(client, db_session, 710005, bot_token)
    resp = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": day})
    assert resp.status_code == 409


async def test_catch_up_limit_per_month(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 710006, bot_token)
    user.balance = 5000
    await db_session.commit()
    for n in range(1, 6):
        ok = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": f"2026-10-0{n}"})
        assert ok.status_code == 200, ok.json()
    blocked = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-06"})
    assert blocked.status_code == 409


async def test_catch_up_needs_enough_coins(client, db_session, bot_token):
    headers, user = await _register(client, db_session, 710007, bot_token)
    user.balance = 10
    await db_session.commit()
    resp = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-02"})
    assert resp.json()["error"]["code"] == "insufficient_balance"


async def test_month_bonus_after_every_day_is_claimed(client, db_session, bot_token, monkeypatch):
    from app.models.enums import Rarity

    await create_player(db_session, rarity=Rarity.legendary)
    monkeypatch.setattr(daily_reward_service, "local_today", lambda: date(2026, 10, 31))
    headers, user = await _register(client, db_session, 710008, bot_token)
    for n in range(1, 31):
        if n != 5:
            db_session.add(DailyReward(user_id=user.id, reward_date=date(2026, 10, n), streak_day=n, coins_awarded=0))
    await db_session.commit()

    body = (await client.post("/api/v1/daily-rewards/claim", headers=headers)).json()
    assert body["month_bonus"] is None  # the 5th is still missing

    final = await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-05"})
    assert final.status_code == 200, final.json()
    bonus = final.json()["month_bonus"]
    assert bonus is not None and bonus["coins"] == 2000 and len(bonus["cards"]) == 1

    calendar = (await client.get("/api/v1/daily-rewards/calendar", headers=headers)).json()
    assert calendar["month_bonus_claimed"] is True and calendar["claimed_count"] == 31
    count = (await db_session.execute(select(func.count(LoginCalendarBonusClaim.id)).where(
        LoginCalendarBonusClaim.user_id == user.id,
    ))).scalar_one()
    assert count == 1


async def test_catch_up_with_stars_goes_through_the_payment_flow(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_link)
    headers, user = await _register(client, db_session, 710009, bot_token)

    invoice = await client.post(
        "/api/v1/daily-rewards/catch-up/stars-invoice", headers=headers, json={"date": "2026-10-04"},
    )
    assert invoice.status_code == 200
    token = invoice.json()["payload_token"]
    assert invoice.json()["stars_amount"] == 10

    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL_HEADERS,
                            json={"payload_token": token, "total_amount": 10})
    assert pre.json()["ok"] is True

    resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL_HEADERS, json={
        "payload_token": token, "telegram_user_id": 710009, "telegram_payment_charge_id": "cal-1", "total_amount": 10,
    })
    assert resp.status_code == 200
    assert resp.json()["shop_result"]["kind"] == "calendar_catchup"
    row = (await db_session.execute(select(DailyReward).where(
        DailyReward.user_id == user.id, DailyReward.reward_date == date(2026, 10, 4),
    ))).scalar_one()
    assert row.claim_method == "stars"

    # The day is taken now — a second invoice for it is refused at pre-checkout.
    status = await client.get(f"/api/v1/shop/stars-invoices/{token}", headers=headers)
    assert status.json()["status"] == "completed"
    inv = (await db_session.execute(select(StarsInvoice).where(StarsInvoice.payload_token == token))).scalar_one()
    assert inv.shop_product == "calendar_catchup:2026-10-04"


async def test_stars_catch_up_of_an_already_claimed_day_compensates(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_link)
    headers, user = await _register(client, db_session, 710010, bot_token)
    token = (await client.post(
        "/api/v1/daily-rewards/catch-up/stars-invoice", headers=headers, json={"date": "2026-10-04"},
    )).json()["payload_token"]
    # A coins catch-up of the same day lands first.
    assert (await client.post("/api/v1/daily-rewards/catch-up", headers=headers, json={"date": "2026-10-04"})).status_code == 200
    await db_session.refresh(user)
    before = user.balance

    resp = await client.post("/api/v1/internal/stars-payments/deliver", headers=INTERNAL_HEADERS, json={
        "payload_token": token, "telegram_user_id": 710010, "telegram_payment_charge_id": "cal-2", "total_amount": 10,
    })
    assert resp.status_code == 200
    assert resp.json()["shop_result"]["compensated"] is True
    await db_session.refresh(user)
    assert user.balance == before + 150


async def test_admin_edits_the_template(client, db_session, bot_token):
    pack = await create_pack(db_session, "cal-pack", price=100, card_count=1, probabilities={"common": 1.0})
    await create_player(db_session)
    auth = await _admin_auth(client, bot_token)
    template = (await client.get("/api/v1/admin/login-calendar", headers=auth)).json()
    assert {d["day"] for d in template} == set(range(0, 32))

    resp = await client.put("/api/v1/admin/login-calendar", headers=auth, json={"days": [
        {"day": 16, "coins": 777, "pack_id": pack.id},
    ]})
    assert resp.status_code == 200
    row = (await db_session.execute(select(LoginCalendarDay).where(LoginCalendarDay.day == 16))).scalar_one()
    assert row.coins == 777 and row.pack_id == pack.id

    headers, _ = await _register(client, db_session, 710011, bot_token)
    body = (await client.post("/api/v1/daily-rewards/claim", headers=headers)).json()
    assert body["granted"]["coins"] == 777 and body["granted"]["pack_name"] == pack.name


async def test_admin_template_rejects_unknown_pack(client, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.put("/api/v1/admin/login-calendar", headers=auth, json={"days": [{"day": 3, "pack_id": 9999}]})
    assert resp.status_code == 409
