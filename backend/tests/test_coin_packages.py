from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


def _package_payload(**overrides):
    payload = {"stars_price": 10, "coins_amount": 20, "is_active": True, "sort_order": 0}
    payload.update(overrides)
    return payload


async def test_create_and_list_coin_package(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post("/api/v1/admin/coin-packages", headers=auth, json=_package_payload())
    assert resp.status_code == 200
    assert resp.json()["coins_amount"] == 20

    list_resp = await client.get("/api/v1/admin/coin-packages", headers=auth)
    assert any(p["stars_price"] == 10 for p in list_resp.json())


async def test_admin_list_includes_inactive_packages(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    await client.post("/api/v1/admin/coin-packages", headers=auth, json=_package_payload(is_active=False))

    list_resp = await client.get("/api/v1/admin/coin-packages", headers=auth)
    assert any(not p["is_active"] for p in list_resp.json())


async def test_update_coin_package_persists(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/coin-packages", headers=auth, json=_package_payload())
    package_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/admin/coin-packages/{package_id}", headers=auth, json={"coins_amount": 25}
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["coins_amount"] == 25
    assert update_resp.json()["stars_price"] == 10  # untouched fields survive a partial update


async def test_delete_coin_package(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/coin-packages", headers=auth, json=_package_payload())
    package_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/admin/coin-packages/{package_id}", headers=auth)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/admin/coin-packages", headers=auth)
    assert all(p["id"] != package_id for p in list_resp.json())
