from tests.utils import telegram_headers


async def test_claim_daily_reward(client, db_session, bot_token):
    headers = telegram_headers(710001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["streak_day"] == 1
    assert body["coins_awarded"] == 50
    assert body["new_balance"] == 550


async def test_claim_daily_reward_twice_same_day_fails(client, bot_token):
    headers = telegram_headers(710002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    first = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    second = await client.post("/api/v1/daily-rewards/claim", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_daily_reward_calendar_reflects_claim_state(client, bot_token):
    headers = telegram_headers(710003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    before = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert before.json()["already_claimed_today"] is False

    await client.post("/api/v1/daily-rewards/claim", headers=headers)

    after = await client.get("/api/v1/daily-rewards/calendar", headers=headers)
    assert after.json()["already_claimed_today"] is True
