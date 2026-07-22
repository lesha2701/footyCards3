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
