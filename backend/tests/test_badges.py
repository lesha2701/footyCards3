from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


def _badge_payload(**overrides):
    payload = {"name": "Test Badge", "icon": "🏆", "is_active": True, "sort_order": 0}
    payload.update(overrides)
    return payload


async def test_create_and_list_badge(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post("/api/v1/admin/badges", headers=auth, json=_badge_payload())
    assert resp.status_code == 200
    assert resp.json()["icon"] == "🏆"

    list_resp = await client.get("/api/v1/admin/badges", headers=auth)
    assert any(b["name"] == "Test Badge" for b in list_resp.json())


async def test_update_badge_persists(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/badges", headers=auth, json=_badge_payload())
    badge_id = create_resp.json()["id"]

    update_resp = await client.put(f"/api/v1/admin/badges/{badge_id}", headers=auth, json={"is_active": False})
    assert update_resp.status_code == 200
    assert update_resp.json()["is_active"] is False
    assert update_resp.json()["name"] == "Test Badge"  # untouched fields survive a partial update


async def test_delete_badge(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/badges", headers=auth, json=_badge_payload())
    badge_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/admin/badges/{badge_id}", headers=auth)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/admin/badges", headers=auth)
    assert all(b["id"] != badge_id for b in list_resp.json())


async def test_upload_and_remove_badge_image(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/badges", headers=auth, json=_badge_payload())
    badge_id = create_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/admin/badges/{badge_id}/image",
        headers=auth,
        files={"file": ("badge.png", b"\x89PNG\r\n\x1a\nfake-bytes", "image/png")},
    )
    assert upload_resp.status_code == 200
    image_path = upload_resp.json()["image_path"]
    assert image_path is not None
    assert image_path.startswith("badges/uploads/")

    list_resp = await client.get("/api/v1/admin/badges", headers=auth)
    assert next(b for b in list_resp.json() if b["id"] == badge_id)["image_path"] == image_path

    remove_resp = await client.delete(f"/api/v1/admin/badges/{badge_id}/image", headers=auth)
    assert remove_resp.status_code == 200
    assert remove_resp.json()["image_path"] is None
