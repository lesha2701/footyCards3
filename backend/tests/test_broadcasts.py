from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_update_status_defaults_to_no_broadcast(client, bot_token):
    headers = telegram_headers(770101, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/updates/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"broadcast_at": None}


async def test_non_admin_cannot_send_broadcast(client, bot_token):
    headers = telegram_headers(770102, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/admin/broadcasts", headers=headers, json={"message": "Вышел патч!"})
    assert resp.status_code == 401


async def test_admin_broadcast_reaches_all_users_and_updates_status(client, bot_token):
    auth = await _admin_auth(client, bot_token)

    headers_a = telegram_headers(770103, bot_token)
    headers_b = telegram_headers(770104, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    await client.post("/api/v1/auth/session", headers=headers_b)

    resp = await client.post("/api/v1/admin/broadcasts", headers=auth, json={"message": "Вышло обновление!"})
    assert resp.status_code == 200
    body = resp.json()
    # includes the admin account itself plus both registered players
    assert body["recipients"] >= 3
    assert body["broadcast_at"] is not None

    for headers in (headers_a, headers_b):
        notifications_resp = await client.get("/api/v1/notifications", headers=headers)
        assert notifications_resp.status_code == 200
        matching = [n for n in notifications_resp.json() if n["body"] == "Вышло обновление!"]
        assert len(matching) == 1
        assert matching[0]["type"] == "admin_message"

        status_resp = await client.get("/api/v1/updates/status", headers=headers)
        assert status_resp.json()["broadcast_at"] is not None


async def test_broadcast_requires_non_empty_message(client, bot_token):
    auth = await _admin_auth(client, bot_token)

    resp = await client.post("/api/v1/admin/broadcasts", headers=auth, json={"message": ""})
    assert resp.status_code == 422
