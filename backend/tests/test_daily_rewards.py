from datetime import timedelta

from sqlalchemy import select

from app.core.timeutil import local_today
from app.models.daily_reward import DailyReward
from tests.factories import get_user_by_telegram_id
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

    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 1
    assert profile.json()["referral_referrer_reward"] > 0
    assert profile.json()["referral_referred_reward"] > 0


async def _latest_reward_row(db_session, user_id: int) -> DailyReward:
    result = await db_session.execute(
        select(DailyReward).where(DailyReward.user_id == user_id).order_by(DailyReward.reward_date.desc()).limit(1)
    )
    return result.scalar_one()


async def test_daily_login_streak_grows_and_resets(client, db_session, bot_token):
    headers = telegram_headers(710010, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 710010)

    await client.post("/api/v1/daily-rewards/claim", headers=headers)

    # Back-date the claim to yesterday so the next claim is on a consecutive day.
    row = await _latest_reward_row(db_session, user.id)
    row.reward_date = local_today() - timedelta(days=1)
    db_session.add(row)
    await db_session.commit()

    resp = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert resp.status_code == 200
    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 2

    # Push every existing claim several days into the past — the streak should
    # reset to 1 on the next claim, not keep growing.
    rows = (await db_session.execute(select(DailyReward).where(DailyReward.user_id == user.id))).scalars().all()
    for i, r in enumerate(rows):
        r.reward_date = local_today() - timedelta(days=5 + i)
        db_session.add(r)
    await db_session.commit()

    resp = await client.post("/api/v1/daily-rewards/claim", headers=headers)
    assert resp.status_code == 200
    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 1


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
