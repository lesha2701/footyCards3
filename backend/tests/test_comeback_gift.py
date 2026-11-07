from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.dependencies import clean_source
from app.models.comeback_gift import ComebackGift
from app.models.user import User
from app.services.game_config_service import get_config
from tests.utils import telegram_headers


async def _config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


async def _away(db_session, telegram_id: int, days: int) -> User:
    user = (await db_session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one()
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=days)
    await db_session.commit()
    return user


async def _gifts(db_session, user_id: int) -> int:
    return (await db_session.execute(
        select(func.count()).select_from(ComebackGift).where(ComebackGift.user_id == user_id)
    )).scalar_one()


async def test_gift_after_a_week_away_once_with_a_popup(client, db_session, bot_token):
    await _config(db_session, comeback_gift_coins=500, comeback_gift_pack_slug="")
    headers = telegram_headers(71001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await _away(db_session, 71001, 8)
    balance = user.balance

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    await client.get("/api/v1/auth/me", headers=headers)
    popup = (await client.get("/api/v1/comeback-gifts/unseen", headers=headers)).json()
    assert len(popup) == 1 and popup[0]["days_away"] == 8 and popup[0]["rewards"]["coins"] == 500
    await db_session.refresh(user)
    assert user.balance == balance + 500

    assert (await client.post(f"/api/v1/comeback-gifts/{popup[0]['id']}/seen", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/comeback-gifts/unseen", headers=headers)).json() == []


async def test_no_gift_for_a_short_absence_or_a_new_player(client, db_session, bot_token):
    await _config(db_session, comeback_gift_coins=500, comeback_gift_pack_slug="")
    headers = telegram_headers(71002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await _away(db_session, 71002, 6)
    await client.get("/api/v1/auth/me", headers=headers)
    assert await _gifts(db_session, user.id) == 0


async def test_cooldown_stops_weekly_returns_from_farming_it(client, db_session, bot_token):
    await _config(db_session, comeback_gift_coins=500, comeback_gift_pack_slug="", comeback_gift_cooldown_days=30)
    headers = telegram_headers(71003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await _away(db_session, 71003, 8)
    await client.get("/api/v1/auth/me", headers=headers)
    await _away(db_session, 71003, 8)
    await client.get("/api/v1/auth/me", headers=headers)
    assert await _gifts(db_session, user.id) == 1

    row = (await db_session.execute(select(ComebackGift).where(ComebackGift.user_id == user.id))).scalar_one()
    row.granted_at = datetime.now(timezone.utc) - timedelta(days=31)
    row.gift_date = (datetime.now(timezone.utc) - timedelta(days=31)).date()
    await db_session.commit()
    await _away(db_session, 71003, 8)
    await client.get("/api/v1/auth/me", headers=headers)
    assert await _gifts(db_session, user.id) == 2


async def test_switched_off(client, db_session, bot_token):
    await _config(db_session, comeback_gift_enabled=False)
    headers = telegram_headers(71004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await _away(db_session, 71004, 20)
    await client.get("/api/v1/auth/me", headers=headers)
    assert await _gifts(db_session, user.id) == 0


async def test_source_is_stored_once_at_registration(client, db_session, bot_token):
    headers = telegram_headers(71005, bot_token)
    await client.post("/api/v1/auth/session", headers={**headers, "X-Start-Source": "penalty_vans"})
    await client.post("/api/v1/auth/session", headers={**headers, "X-Start-Source": "penalty_meta"})
    user = (await db_session.execute(select(User).where(User.telegram_id == 71005))).scalar_one()
    assert user.acquisition_source == "penalty_vans"


def test_source_alphabet():
    assert clean_source("penalty_vans-2") == "penalty_vans-2"
    assert clean_source("<script>") is None and clean_source("x" * 65) is None and clean_source(None) is None
