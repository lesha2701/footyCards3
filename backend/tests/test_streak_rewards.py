from datetime import datetime, timedelta, timezone

from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_keepsake_for_days_in_a_row_once_with_a_popup(client, db_session, bot_token):
    config = await get_config(db_session)
    config.streak_rewards = [{"days": 3, "coins": 500}]
    await db_session.commit()
    headers = telegram_headers(870501, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 870501)
    user.daily_login_streak = 2
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    balance = user.balance

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    await db_session.refresh(user)
    assert user.daily_login_streak == 3 and user.balance == balance + 500
    popup = (await client.get("/api/v1/streak-rewards/unseen", headers=headers)).json()
    assert len(popup) == 1 and popup[0]["days"] == 3 and popup[0]["rewards"]["coins"] == 500

    assert (await client.post(f"/api/v1/streak-rewards/{popup[0]['id']}/seen", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/streak-rewards/unseen", headers=headers)).json() == []

    # Next day the streak goes on — the milestone isn't paid again.
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    await client.get("/api/v1/auth/me", headers=headers)
    await db_session.refresh(user)
    assert user.daily_login_streak == 4 and user.balance == balance + 500
