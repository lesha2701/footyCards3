from tests.utils import telegram_headers


async def _admin_token(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    resp = await client.post("/api/v1/auth/session", headers=headers)
    return resp.json()["admin_token"]


async def test_admin_coaches_routes_reject_missing_token(client):
    resp = await client.get("/api/v1/admin/coaches")
    assert resp.status_code == 401


async def test_admin_can_create_list_and_update_coach(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={
            "display_name": "Пеп Хренандес", "rarity": "legendary", "quick_sell_price": 50,
            "boosts": [
                {"boost_type": "attack_central", "magnitude": 6.0},
                {"boost_type": "defence_central", "magnitude": 6.0},
                {"boost_type": "goalkeeping", "magnitude": 4.0},
            ],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    coach_id = create_resp.json()["id"]
    assert len(create_resp.json()["boosts"]) == 3

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    assert list_resp.status_code == 200
    assert any(c["id"] == coach_id for c in list_resp.json()["items"])

    update_resp = await client.put(
        f"/api/v1/admin/coaches/{coach_id}", headers=auth, json={"display_name": "Пеп Хренандес II"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["display_name"] == "Пеп Хренандес II"
    assert len(update_resp.json()["boosts"]) == 3  # untouched by the partial update


async def test_create_coach_rejects_bad_rarity_boost_count(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/coaches", headers={"Authorization": f"Bearer {token}"},
        json={
            "display_name": "Under-boosted", "rarity": "legendary",
            "boosts": [{"boost_type": "attack_central", "magnitude": 4.0}],
        },
    )
    assert resp.status_code == 422


async def test_toggle_active_and_delete_coach(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={"display_name": "Togglable Coach", "rarity": "common", "boosts": [{"boost_type": "ball_control", "magnitude": 1.0}]},
    )
    coach_id = create_resp.json()["id"]

    toggle_resp = await client.post(f"/api/v1/admin/coaches/{coach_id}/toggle-active", headers=auth)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/admin/coaches/{coach_id}", headers=auth)
    assert delete_resp.status_code == 200

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    assert all(c["id"] != coach_id for c in list_resp.json()["items"])
