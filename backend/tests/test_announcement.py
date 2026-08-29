from tests.utils import telegram_headers


async def test_announcement_defaults_to_empty(client, bot_token):
    headers = telegram_headers(761101, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/announcement", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"text": None, "updated_at": None}


async def test_non_admin_cannot_set_announcement(client, bot_token):
    headers = telegram_headers(761102, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/admin/announcement", json={"text": "hi"}, headers=headers)
    assert resp.status_code == 401


async def test_admin_can_set_and_clear_announcement(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    set_resp = await client.post("/api/v1/admin/announcement", json={"text": "Идёт турнир!"}, headers=auth_headers)
    assert set_resp.status_code == 200
    body = set_resp.json()
    assert body["text"] == "Идёт турнир!"
    assert body["updated_at"] is not None
    first_updated_at = body["updated_at"]

    status_resp = await client.get("/api/v1/announcement", headers=admin_headers)
    assert status_resp.json()["text"] == "Идёт турнир!"

    # Setting new text bumps updated_at so a client that already dismissed the
    # old text sees the banner again.
    set_resp2 = await client.post("/api/v1/admin/announcement", json={"text": "Новый текст"}, headers=auth_headers)
    assert set_resp2.json()["text"] == "Новый текст"
    assert set_resp2.json()["updated_at"] != first_updated_at

    clear_resp = await client.post("/api/v1/admin/announcement", json={"text": "   "}, headers=auth_headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json()["text"] is None

    status_resp2 = await client.get("/api/v1/announcement", headers=admin_headers)
    assert status_resp2.json()["text"] is None
