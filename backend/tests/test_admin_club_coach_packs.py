from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_club_coach_pack_requires_probabilities_summing_to_one(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/club-coach-packs", headers=auth,
        json={
            "slug": "coach-basic", "name": "Тренерский базовый", "price": 500, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 0.5}],
        },
    )
    assert resp.status_code == 409


async def test_create_and_update_club_coach_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/club-coach-packs", headers=auth,
        json={
            "slug": "coach-premium", "name": "Тренерский премиум", "price": 1000, "card_count": 1,
            "rarity_probabilities": [
                {"rarity": "common", "probability": 0.6}, {"rarity": "rare", "probability": 0.3}, {"rarity": "epic", "probability": 0.1},
            ],
        },
    )
    assert create_resp.status_code == 200
    pack_id = create_resp.json()["id"]
    assert len(create_resp.json()["rarity_probabilities"]) == 3

    update_resp = await client.put(f"/api/v1/admin/club-coach-packs/{pack_id}", headers=auth, json={"price": 1500})
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 1500

    list_resp = await client.get("/api/v1/admin/club-coach-packs", headers=auth)
    assert any(p["id"] == pack_id for p in list_resp.json())


async def test_delete_club_coach_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/club-coach-packs", headers=auth,
        json={
            "slug": "coach-to-delete", "name": "Тренерский на удаление", "price": 700, "card_count": 1,
            "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
        },
    )
    assert create_resp.status_code == 200
    pack_id = create_resp.json()["id"]

    delete_resp = await client.delete(f"/api/v1/admin/club-coach-packs/{pack_id}", headers=auth)
    assert delete_resp.status_code == 204

    list_resp = await client.get("/api/v1/admin/club-coach-packs", headers=auth)
    assert not any(p["id"] == pack_id for p in list_resp.json())
