from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_admin_can_create_and_grant_trophy(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    player_headers = telegram_headers(770001, bot_token)
    await client.post("/api/v1/auth/session", headers=player_headers)
    user = await get_user_by_telegram_id(db_session, 770001)

    create_resp = await client.post(
        "/api/v1/admin/trophies", headers=auth,
        json={"code": "legend", "name": "Легенда", "description": "test", "icon": "🏅"},
    )
    assert create_resp.status_code == 200
    trophy_id = create_resp.json()["id"]

    grant_resp = await client.post(
        f"/api/v1/admin/users/{user.id}/trophies/grant", headers=auth,
        json={"trophy_definition_id": trophy_id, "message": "За заслуги!"},
    )
    assert grant_resp.status_code == 200
    assert grant_resp.json()["trophy"]["code"] == "legend"
    assert grant_resp.json()["message"] == "За заслуги!"

    my_resp = await client.get("/api/v1/profile/trophies", headers=player_headers)
    assert my_resp.status_code == 200
    assert len(my_resp.json()) == 1
    assert my_resp.json()[0]["trophy"]["name"] == "Легенда"

    notifications_resp = await client.get("/api/v1/notifications", headers=player_headers)
    assert notifications_resp.status_code == 200
    notification_types = [n["type"] for n in notifications_resp.json()]
    assert "trophy_granted" in notification_types


async def test_non_admin_cannot_grant_trophy(client, db_session, bot_token):
    headers = telegram_headers(770002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 770002)

    resp = await client.post(
        f"/api/v1/admin/users/{user.id}/trophies/grant", headers=headers,
        json={"trophy_definition_id": 1},
    )
    assert resp.status_code == 401


async def test_granting_unknown_trophy_404s(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    headers = telegram_headers(770003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 770003)

    resp = await client.post(
        f"/api/v1/admin/users/{user.id}/trophies/grant", headers=auth,
        json={"trophy_definition_id": 999999},
    )
    assert resp.status_code == 404


async def test_deleting_trophy_definition_removes_it_from_profiles(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)

    headers = telegram_headers(770004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 770004)

    create_resp = await client.post(
        "/api/v1/admin/trophies", headers=auth, json={"code": "temp_trophy", "name": "Temp"},
    )
    trophy_id = create_resp.json()["id"]
    await client.post(
        f"/api/v1/admin/users/{user.id}/trophies/grant", headers=auth,
        json={"trophy_definition_id": trophy_id},
    )

    delete_resp = await client.delete(f"/api/v1/admin/trophies/{trophy_id}", headers=auth)
    assert delete_resp.status_code == 204

    my_resp = await client.get("/api/v1/profile/trophies", headers=headers)
    assert my_resp.json() == []
