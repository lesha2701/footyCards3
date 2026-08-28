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


async def test_feature_flags_default_enabled_and_toggle_hides_them(client, db_session, bot_token):
    user_headers = telegram_headers(760003, bot_token)
    await client.post("/api/v1/auth/session", headers=user_headers)

    resp = await client.get("/api/v1/feature-flags", headers=user_headers)
    assert resp.status_code == 200
    assert resp.json() == {"matchmaking_enabled": True, "wheel_enabled": True, "leagues_enabled": True}

    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    update_resp = await client.put(
        "/api/v1/admin/games/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"matchmaking_enabled": False, "wheel_enabled": False, "leagues_enabled": False},
    )
    assert update_resp.status_code == 200

    resp2 = await client.get("/api/v1/feature-flags", headers=user_headers)
    assert resp2.json() == {"matchmaking_enabled": False, "wheel_enabled": False, "leagues_enabled": False}


async def test_admin_toggle_trade_ban(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    target_headers = telegram_headers(760004, bot_token)
    await client.post("/api/v1/auth/session", headers=target_headers)
    target = await get_user_by_telegram_id(db_session, 760004)
    assert target.is_trade_banned is False

    resp = await client.post(
        f"/api/v1/admin/users/{target.id}/toggle-trade-ban",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_trade_banned"] is True

    resp2 = await client.post(
        f"/api/v1/admin/users/{target.id}/toggle-trade-ban",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp2.json()["is_trade_banned"] is False


async def test_admin_can_update_club_tournament_game_config_fields(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.put(
        "/api/v1/admin/games/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "club_tournament_cooldown_hours": 4,
            "club_form_window_matches": 5,
            "club_form_bonus_per_result": 0.05,
            "club_tournament_budget_place_1": 1200,
            "club_tournament_budget_place_2": 900,
            "club_tournament_budget_place_3": 700,
            "club_tournament_budget_place_4": 500,
            "club_tournament_budget_place_5": 350,
            "club_tournament_budget_place_6": 250,
            "club_tournament_budget_place_7": 150,
            "club_tournament_budget_place_8": 80,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["club_tournament_cooldown_hours"] == 4
    assert body["club_form_window_matches"] == 5
    assert body["club_form_bonus_per_result"] == 0.05
    assert body["club_tournament_budget_place_1"] == 1200
    assert body["club_tournament_budget_place_8"] == 80

    get_resp = await client.get(
        "/api/v1/admin/games/config", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert get_resp.json()["club_tournament_budget_place_1"] == 1200


async def test_admin_cannot_set_club_form_bonus_above_one(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    admin_token = session_resp.json()["admin_token"]

    resp = await client.put(
        "/api/v1/admin/games/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"club_form_bonus_per_result": 1.5},
    )
    assert resp.status_code == 422
