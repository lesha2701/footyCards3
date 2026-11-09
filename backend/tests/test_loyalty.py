from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.core.timeutil import local_today
from app.models.badge import UserBadge
from app.models.card import UserCard
from app.models.enums import Rarity
from app.models.monetization import ClubSubscription
from app.models.streak_reward import StreakReward
from app.models.user_activity import UserDailyActivity
from app.services import stars_payment_service
from app.services.game_config_service import get_config
from tests.factories import create_badge, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}


async def _register(client, db_session, bot_token, tg: int):
    headers = telegram_headers(tg, bot_token)
    assert (await client.post("/api/v1/auth/session", headers=headers)).status_code == 200
    return headers, await get_user_by_telegram_id(db_session, tg)


async def _centurion(db_session, **settings):
    player = await create_player(db_session, rarity=Rarity.legendary, rating=95, is_pack_droppable=False,
                                 display_name="Франц Беккенбауэр · Центурион")
    purple = await create_badge(db_session, name="Центурион", icon="💜")
    config = await get_config(db_session)
    config.streak_rewards = [{"days": 100, "coins": 25000, "player_id": player.id, "badge_id": purple.id}]
    config.loyalty_settings = {"centurion_player_id": player.id, "centurion_badge_id": purple.id, **settings}
    await db_session.commit()
    return player, purple


async def _new_day(client, db_session, headers, user, days_ago: int = 1):
    user.last_seen_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    await db_session.commit()
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    await db_session.refresh(user)


async def test_hundred_days_in_a_row_gives_the_centurion_bound_forever(client, db_session, bot_token):
    player, purple = await _centurion(db_session)
    headers, user = await _register(client, db_session, bot_token, 871001)
    user.daily_login_streak = 99
    await db_session.commit()
    balance = user.balance

    await _new_day(client, db_session, headers, user)
    assert user.daily_login_streak == 100 and user.balance == balance + 25000
    card = (await db_session.execute(
        select(UserCard).where(UserCard.owner_id == user.id, UserCard.player_id == player.id)
    )).scalar_one()
    assert card.is_bound_forever() and card.is_locked() and card.is_user_locked
    assert (await db_session.execute(
        select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == purple.id)
    )).first()
    # It can't be unlocked, sold or put up on the market.
    unlock = await client.patch("/api/v1/collection/cards/lock", headers=headers,
                                json={"card_ids": [card.id], "locked": False})
    assert unlock.status_code == 409
    status = (await client.get("/api/v1/loyalty/status", headers=headers)).json()
    assert status["centurion_owned"] and status["centurion"]["display_name"] == "Франц Беккенбауэр · Центурион"
    # No double card from the backpay check.
    assert (await client.get("/api/v1/loyalty/unseen", headers=headers)).json() == []


async def test_centurion_backpay_for_who_reached_100_before(client, db_session, bot_token):
    player, _ = await _centurion(db_session)
    headers, user = await _register(client, db_session, bot_token, 871002)
    db_session.add(StreakReward(user_id=user.id, days=100, rewards={"coins": 25000}))
    user.daily_login_streak = 120
    await db_session.commit()

    # Same day, no new visit day: the popup request itself grants it.
    popup = (await client.get("/api/v1/loyalty/unseen", headers=headers)).json()
    owned = (await db_session.execute(
        select(UserCard.id).where(UserCard.owner_id == user.id, UserCard.player_id == player.id)
    )).scalars().all()
    assert len(owned) == 1
    assert [p["code"] for p in popup] == ["centurion"]
    assert popup[0]["rewards"]["cards"][0]["player"]["id"] == player.id
    assert (await client.post(f"/api/v1/loyalty/{popup[0]['id']}/seen", headers=headers)).status_code == 204

    await _new_day(client, db_session, headers, user)
    assert len((await db_session.execute(
        select(UserCard.id).where(UserCard.owner_id == user.id, UserCard.player_id == player.id)
    )).scalars().all()) == 1


async def test_oldtimer_needs_100_days_and_50_active(client, db_session, bot_token):
    await create_player(db_session, rarity=Rarity.legendary, rating=90)
    green = await create_badge(db_session, name="Старожил", icon="💚")
    config = await get_config(db_session)
    config.loyalty_settings = {"oldtimer_badge_id": green.id}
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 871003)
    user.created_at = datetime.now(timezone.utc) - timedelta(days=120)
    today = local_today()
    for i in range(2, 50):  # 48 older days + yesterday/today = 50 at the second visit
        db_session.add(UserDailyActivity(user_id=user.id, day=today - timedelta(days=i)))
    await db_session.commit()

    await _new_day(client, db_session, headers, user)
    assert (await client.get("/api/v1/loyalty/unseen", headers=headers)).json() == []  # 49 active days

    db_session.add(UserDailyActivity(user_id=user.id, day=today - timedelta(days=1)))
    await db_session.commit()
    await _new_day(client, db_session, headers, user)
    popup = (await client.get("/api/v1/loyalty/unseen", headers=headers)).json()
    assert [p["code"] for p in popup] == ["oldtimer"]
    assert popup[0]["rewards"]["badge"]["name"] == "Старожил"
    assert popup[0]["rewards"]["cards"][0]["player"]["rarity"] == "legendary"


async def test_founder_only_for_the_first_players(client, db_session, bot_token):
    gold = await create_badge(db_session, name="Основатель", icon="🏛️")
    config = await get_config(db_session)
    config.loyalty_settings = {"founder_badge_id": gold.id, "founder_limit": 1}
    await db_session.commit()
    first_headers, first = await _register(client, db_session, bot_token, 871004)
    second_headers, second = await _register(client, db_session, bot_token, 871005)

    await _new_day(client, db_session, first_headers, first)
    await _new_day(client, db_session, second_headers, second)
    assert [p["code"] for p in (await client.get("/api/v1/loyalty/unseen", headers=first_headers)).json()] == ["founder"]
    assert (await client.get("/api/v1/loyalty/unseen", headers=second_headers)).json() == []


async def test_streak_save_free_with_the_club_pass_once_a_month(client, db_session, bot_token):
    headers, user = await _register(client, db_session, bot_token, 871006)
    user.daily_login_streak = 40
    db_session.add(ClubSubscription(user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=10)))
    await db_session.commit()

    await _new_day(client, db_session, headers, user, days_ago=2)  # missed one day
    assert user.daily_login_streak == 1 and user.streak_saved_value == 40
    save = (await client.get("/api/v1/loyalty/status", headers=headers)).json()["streak_save"]
    assert save["saved_streak"] == 40 and save["restored_streak"] == 41 and save["free_available"]

    restored = await client.post("/api/v1/loyalty/streak-save/free", headers=headers)
    assert restored.status_code == 200 and restored.json()["streak"] == 41
    assert (await client.get("/api/v1/loyalty/status", headers=headers)).json()["streak_save"] is None

    # Broken again the same month: the free one is used up.
    await _new_day(client, db_session, headers, user, days_ago=2)
    assert (await client.get("/api/v1/loyalty/status", headers=headers)).json()["streak_save"]["free_available"] is False
    assert (await client.post("/api/v1/loyalty/streak-save/free", headers=headers)).status_code == 409


async def test_streak_save_not_for_short_streaks_or_long_breaks(client, db_session, bot_token):
    headers, user = await _register(client, db_session, bot_token, 871007)
    user.daily_login_streak = 3
    await db_session.commit()
    await _new_day(client, db_session, headers, user, days_ago=2)
    assert user.streak_saved_value is None

    user.daily_login_streak = 30
    await db_session.commit()
    await _new_day(client, db_session, headers, user, days_ago=3)  # two days missed
    assert user.streak_saved_value is None and user.daily_login_streak == 1
    assert (await client.post("/api/v1/loyalty/streak-save/stars-invoice", headers=headers)).status_code == 409


async def test_streak_save_for_stars(client, db_session, bot_token, monkeypatch):
    async def fake_link(payload_token, title, description, stars_amount, subscription_period=None):
        return f"https://t.me/invoice/{payload_token}"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    config = await get_config(db_session)
    config.loyalty_settings = {"streak_save_stars": 75}
    await db_session.commit()
    headers, user = await _register(client, db_session, bot_token, 871008)
    user.daily_login_streak = 25
    await db_session.commit()
    await _new_day(client, db_session, headers, user, days_ago=2)

    invoice = await client.post("/api/v1/loyalty/streak-save/stars-invoice", headers=headers)
    assert invoice.status_code == 200, invoice.text
    body = invoice.json()
    assert body["stars_amount"] == 75
    pre = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": body["payload_token"], "total_amount": 75}, headers=INTERNAL_HEADERS,
    )
    assert pre.json()["ok"] is True, pre.json()
    deliver = {"payload_token": body["payload_token"], "telegram_user_id": 871008,
               "telegram_payment_charge_id": "ch-streak-1", "total_amount": 75}
    assert (await client.post("/api/v1/internal/stars-payments/deliver", json=deliver,
                              headers=INTERNAL_HEADERS)).status_code == 200
    assert (await client.post("/api/v1/internal/stars-payments/deliver", json=deliver,
                              headers=INTERNAL_HEADERS)).status_code == 200
    await db_session.refresh(user)
    assert user.daily_login_streak == 26 and user.streak_saved_value is None

    # Nothing left to save.
    assert (await client.post("/api/v1/loyalty/streak-save/stars-invoice", headers=headers)).status_code == 409
