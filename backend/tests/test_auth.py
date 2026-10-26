import pytest

from app.core.security import TelegramAuthError, validate_init_data
from tests.utils import make_init_data, telegram_headers


def test_valid_init_data_parses_user(bot_token):
    init_data = make_init_data({"id": 12345, "username": "alice", "first_name": "Alice"}, bot_token)
    user = validate_init_data(init_data, bot_token)
    assert user.id == 12345
    assert user.username == "alice"


def test_tampered_init_data_is_rejected(bot_token):
    init_data = make_init_data({"id": 12345, "username": "alice"}, bot_token)
    tampered = init_data.replace("alice", "mallory")
    with pytest.raises(TelegramAuthError):
        validate_init_data(tampered, bot_token)


def test_wrong_bot_token_is_rejected(bot_token):
    init_data = make_init_data({"id": 12345, "username": "alice"}, bot_token)
    with pytest.raises(TelegramAuthError):
        validate_init_data(init_data, "OTHER:TOKEN")


async def test_registration_creates_user_with_starting_balance(client, bot_token):
    headers = telegram_headers(555001, bot_token, username="newplayer")
    resp = await client.post("/api/v1/auth/session", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["balance"] == 500
    assert body["user"]["telegram_id"] == 555001


async def test_repeat_login_does_not_grant_bonus_twice(client, bot_token):
    headers = telegram_headers(555002, bot_token, username="returning")
    first = await client.post("/api/v1/auth/session", headers=headers)
    second = await client.post("/api/v1/auth/session", headers=headers)
    assert first.json()["user"]["balance"] == 500
    assert second.json()["user"]["balance"] == 500
    assert first.json()["user"]["id"] == second.json()["user"]["id"]


async def test_daily_login_streak_grows_and_resets(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from tests.factories import get_user_by_telegram_id

    headers = telegram_headers(555010, bot_token, username="streaker")
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 555010)
    assert user.daily_login_streak == 0  # registration itself doesn't count as a day yet

    # Any authenticated request on a new calendar day counts — not just this
    # one specific endpoint — so a plain profile fetch is enough.
    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 1

    # A second request the same day must not double-count.
    profile_again = await client.get("/api/v1/profile/me", headers=headers)
    assert profile_again.json()["daily_login_streak"] == 1

    # Simulate having last been active yesterday — the next request should
    # extend the streak.
    await db_session.refresh(user)
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add(user)
    await db_session.commit()

    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 2

    # A multi-day gap resets the streak to 1 instead of continuing to grow.
    await db_session.refresh(user)
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=5)
    db_session.add(user)
    await db_session.commit()

    profile = await client.get("/api/v1/profile/me", headers=headers)
    assert profile.json()["daily_login_streak"] == 1


async def test_dev_mode_login_without_telegram(client):
    resp = await client.get("/api/v1/auth/me", headers={"X-Dev-Mode": "true"})
    assert resp.status_code == 200
    assert resp.json()["telegram_id"] == 999000001


async def test_missing_auth_is_rejected(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_referral_code_links_new_user_without_crediting_referrer_yet(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    referrer_headers = telegram_headers(555010, bot_token, username="referrer")
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 555010)

    new_user_headers = telegram_headers(555011, bot_token, username="newbie")
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    resp = await client.post("/api/v1/auth/session", headers=new_user_headers)
    assert resp.status_code == 200

    new_user = await get_user_by_telegram_id(db_session, 555011)
    await db_session.refresh(referrer)
    assert new_user.referred_by_id == referrer.id
    # Not credited yet: a bare registration must not be enough to farm
    # referral rewards with disposable accounts (referral_service.check_friend).
    assert referrer.referral_count == 0


async def _referral_pair(client, db_session, bot_token, referrer_tg, friend_tg):
    from tests.factories import get_user_by_telegram_id

    await client.post("/api/v1/auth/session", headers=telegram_headers(referrer_tg, bot_token, username=f"r{referrer_tg}"))
    referrer = await get_user_by_telegram_id(db_session, referrer_tg)
    friend_headers = telegram_headers(friend_tg, bot_token, username=f"f{friend_tg}")
    friend_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=friend_headers)
    friend = await get_user_by_telegram_id(db_session, friend_tg)
    return referrer, friend, friend_headers


async def _active_on_past_days(db_session, user, days):
    from datetime import timedelta

    from app.core.timeutil import local_today
    from app.models.user_activity import UserDailyActivity

    for n in range(1, days + 1):
        db_session.add(UserDailyActivity(user_id=user.id, day=local_today() - timedelta(days=n)))
    await db_session.commit()


async def test_referral_counts_only_after_friend_played_three_days(client, db_session, bot_token):
    from sqlalchemy import select

    from app.models.enums import NotificationType, Rarity
    from app.models.notification import Notification
    from app.services import referral_service
    from tests.factories import create_pack, create_player

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    referrer, friend, friend_headers = await _referral_pair(client, db_session, bot_token, 555020, 555021)
    referrer_before, friend_before = referrer.balance, friend.balance

    # A pack is no signal any more: free packs cost nothing.
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=friend_headers, json={})
    assert resp.status_code == 200 and resp.json()["referral_bonus_coins"] is None
    assert await referral_service.check_friend(db_session, friend) is None  # one day so far

    await _active_on_past_days(db_session, friend, 2)
    assert await referral_service.check_friend(db_session, friend) == 2000
    await db_session.refresh(referrer)
    await db_session.refresh(friend)
    assert referrer.referral_count == 1 and friend.referral_reward_granted is True
    assert referrer.balance == referrer_before + 3000
    assert friend.balance == friend_before - pack.price + 2000
    # «Друг присоединился» at sign-up + «Друг засчитан».
    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == referrer.id, Notification.type == NotificationType.referral_joined,
    ))).scalars().all()
    assert len(notes) == 2
    # Never twice.
    assert await referral_service.check_friend(db_session, friend) is None
    await db_session.refresh(referrer)
    assert referrer.referral_count == 1


async def test_referral_checked_on_friends_new_day(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    referrer, friend, friend_headers = await _referral_pair(client, db_session, bot_token, 555022, 555023)
    await _active_on_past_days(db_session, friend, 2)
    friend.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.commit()
    assert (await client.get("/api/v1/auth/me", headers=friend_headers)).status_code == 200
    await db_session.refresh(referrer)
    assert referrer.referral_count == 1


async def test_referral_milestones_pay_once(client, db_session, bot_token):
    from app.services import referral_service
    from app.services.game_config_service import get_config

    config = await get_config(db_session)
    config.referral_milestones = [{"count": 1, "coins": 777}, {"count": 2, "coins": 5000}]
    await db_session.commit()
    referrer, friend, _ = await _referral_pair(client, db_session, bot_token, 555024, 555025)
    before = referrer.balance
    await _active_on_past_days(db_session, friend, 2)
    await referral_service.check_friend(db_session, friend)
    await db_session.refresh(referrer)
    assert referrer.balance == before + 3000 + 777
    assert referrer.referral_milestone_paid == 1


async def test_self_referral_is_a_no_op(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    headers = telegram_headers(555012, bot_token, username="selfref")
    headers["X-Referral-Code"] = "555012"
    resp = await client.post("/api/v1/auth/session", headers=headers)
    assert resp.status_code == 200

    user = await get_user_by_telegram_id(db_session, 555012)
    assert user.referred_by_id is None


async def test_unknown_referrer_is_a_no_op(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    headers = telegram_headers(555013, bot_token, username="norefdad")
    headers["X-Referral-Code"] = "999999999"
    resp = await client.post("/api/v1/auth/session", headers=headers)
    assert resp.status_code == 200

    user = await get_user_by_telegram_id(db_session, 555013)
    assert user.referred_by_id is None
