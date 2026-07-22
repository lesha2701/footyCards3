from app.core.security import create_admin_token
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_admin_routes_reject_missing_token(client):
    resp = await client.get("/api/v1/admin/dashboard")
    assert resp.status_code == 401


async def test_admin_routes_reject_non_admin_user_token(client, db_session, bot_token):
    headers = telegram_headers(760001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 760001)

    fake_admin_token = create_admin_token(user.id, user.telegram_id)
    resp = await client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {fake_admin_token}"})
    assert resp.status_code == 403


async def test_admin_dashboard_accessible_with_valid_admin_token(client, db_session, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = session_resp.json()["admin_token"]
    assert admin_token is not None

    resp = await client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "total_users" in resp.json()


async def test_admin_can_adjust_user_balance(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    target_headers = telegram_headers(760002, bot_token)
    await client.post("/api/v1/auth/session", headers=target_headers)
    target = await get_user_by_telegram_id(db_session, 760002)

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/balance",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"amount": 100, "description": "test grant"},
    )
    assert resp.status_code == 200
    assert resp.json()["balance"] == 600
