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
    # referral rewards with disposable accounts (see pack_service.open_pack
    # for where this is actually credited).
    assert referrer.referral_count == 0


async def test_referral_reward_credited_on_referred_users_first_pack(client, db_session, bot_token):
    from sqlalchemy import select

    from app.models.enums import NotificationType, Rarity
    from app.models.notification import Notification
    from tests.factories import create_pack, create_player, get_user_by_telegram_id

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})

    referrer_headers = telegram_headers(555020, bot_token, username="referrer2")
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 555020)
    referrer_balance_before = referrer.balance

    new_user_headers = telegram_headers(555021, bot_token, username="newbie2")
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=new_user_headers)
    new_user = await get_user_by_telegram_id(db_session, 555021)
    new_user_balance_before = new_user.balance

    await db_session.refresh(referrer)
    assert referrer.referral_count == 0

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["referral_bonus_coins"] == 200

    await db_session.refresh(referrer)
    await db_session.refresh(new_user)
    assert referrer.referral_count == 1
    # Referred user: -100 (pack price) + 200 (referral bonus) = +100 net.
    assert new_user.balance == new_user_balance_before - pack.price + 200
    assert referrer.balance == referrer_balance_before + 400

    # The referrer must be told explicitly, not just have a silent counter bump.
    notifications = (
        await db_session.execute(
            select(Notification).where(
                Notification.user_id == referrer.id, Notification.type == NotificationType.referral_joined
            )
        )
    ).scalars().all()
    assert len(notifications) == 1

    # A second pack by the same referred user must not credit again.
    pack2 = await create_pack(db_session, "basic2", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"/api/v1/packs/{pack2.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200
    assert resp.json()["referral_bonus_coins"] is None

    await db_session.refresh(referrer)
    assert referrer.referral_count == 1
    assert referrer.balance == referrer_balance_before + 400


async def test_referral_reward_triggers_on_free_pack(client, db_session, bot_token):
    from app.models.enums import Rarity
    from tests.factories import create_pack, create_player, get_user_by_telegram_id

    await create_player(db_session, rarity=Rarity.common)
    free_pack = await create_pack(db_session, "free-basic", price=0, card_count=1, probabilities={Rarity.common: 1.0})

    referrer_headers = telegram_headers(555022, bot_token, username="referrer3")
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 555022)

    new_user_headers = telegram_headers(555023, bot_token, username="newbie3")
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=new_user_headers)
    new_user = await get_user_by_telegram_id(db_session, 555023)
    balance_before = new_user.balance

    resp = await client.post(f"/api/v1/packs/{free_pack.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200
    assert resp.json()["referral_bonus_coins"] == 200

    await db_session.refresh(referrer)
    await db_session.refresh(new_user)
    assert referrer.referral_count == 1
    assert new_user.balance == balance_before + 200
    assert new_user.referral_reward_granted is True


async def test_referral_reward_triggers_on_bonus_pack_grant(client, db_session, bot_token):
    """Regression test: pack_service.grant_bonus_pack_opening (shared by
    task rewards, collection-completion rewards, league-tier rewards, and
    wheel-of-fortune bonus packs) used to bypass the referral-credit check
    entirely (only open_pack had it) — a referred user whose first-ever
    pack was one of these server-initiated grants left their referrer
    stuck at referral_count=0 forever."""
    from app.models.enums import Rarity
    from app.services import pack_service
    from app.services.wallet_service import lock_user_for_update
    from tests.factories import create_pack, create_player, get_user_by_telegram_id

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "bonus-pack", price=0, card_count=1, probabilities={Rarity.common: 1.0})

    referrer_headers = telegram_headers(555024, bot_token, username="referrer4")
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 555024)

    new_user_headers = telegram_headers(555025, bot_token, username="newbie4")
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=new_user_headers)
    new_user = await get_user_by_telegram_id(db_session, 555025)
    balance_before = new_user.balance

    locked_user = await lock_user_for_update(db_session, new_user.id)
    result = await pack_service.grant_bonus_pack_opening(
        db_session, locked_user, pack.id, idempotency_prefix="test-bonus-grant",
    )
    await db_session.commit()

    assert result is not None
    assert result.referral_bonus_coins == 200

    await db_session.refresh(referrer)
    await db_session.refresh(new_user)
    assert referrer.referral_count == 1
    assert new_user.balance == balance_before + 200
    assert new_user.referral_reward_granted is True


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
