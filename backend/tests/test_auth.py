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


async def test_referral_count_credited_only_after_referred_users_first_paid_pack(client, db_session, bot_token):
    from tests.factories import create_pack, create_player, get_user_by_telegram_id
    from app.models.enums import Rarity

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "basic", price=100, card_count=1, probabilities={Rarity.common: 1.0})

    referrer_headers = telegram_headers(555020, bot_token, username="referrer2")
    await client.post("/api/v1/auth/session", headers=referrer_headers)
    referrer = await get_user_by_telegram_id(db_session, 555020)

    new_user_headers = telegram_headers(555021, bot_token, username="newbie2")
    new_user_headers["X-Referral-Code"] = str(referrer.telegram_id)
    await client.post("/api/v1/auth/session", headers=new_user_headers)

    await db_session.refresh(referrer)
    assert referrer.referral_count == 0

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200

    await db_session.refresh(referrer)
    assert referrer.referral_count == 1

    # A second paid pack by the same referred user must not credit again.
    pack2 = await create_pack(db_session, "basic2", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"/api/v1/packs/{pack2.id}/open", headers=new_user_headers, json={})
    assert resp.status_code == 200

    await db_session.refresh(referrer)
    assert referrer.referral_count == 1


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
