from tests.utils import telegram_headers


async def test_maintenance_status_defaults_to_inactive(client, bot_token):
    headers = telegram_headers(760101, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/maintenance", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"active": False, "until": None}


async def test_non_admin_cannot_start_maintenance_banner(client, bot_token):
    headers = telegram_headers(760102, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/admin/maintenance/start", headers=headers)
    assert resp.status_code == 401


async def test_admin_can_start_and_clear_maintenance_banner(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    start_resp = await client.post("/api/v1/admin/maintenance/start", headers=auth_headers)
    assert start_resp.status_code == 200
    body = start_resp.json()
    assert body["active"] is True
    assert body["until"] is not None

    status_resp = await client.get("/api/v1/maintenance", headers=admin_headers)
    assert status_resp.json()["active"] is True

    clear_resp = await client.post("/api/v1/admin/maintenance/clear", headers=auth_headers)
    assert clear_resp.status_code == 200
    assert clear_resp.json() == {"active": False, "until": None}

    status_resp = await client.get("/api/v1/maintenance", headers=admin_headers)
    assert status_resp.json() == {"active": False, "until": None}
