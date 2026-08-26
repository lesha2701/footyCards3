from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_create_club_pack_requires_probabilities_summing_to_one(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-basic", "name": "Клубный базовый", "price": 500, "card_count": 3,
            "rarity_probabilities": [{"rarity": "common", "probability": 0.5}],
        },
    )
    assert resp.status_code == 409


async def test_create_and_update_club_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post(
        "/api/v1/admin/club-packs", headers=auth,
        json={
            "slug": "club-premium", "name": "Клубный премиум", "price": 1000, "card_count": 3,
            "rarity_probabilities": [
                {"rarity": "common", "probability": 0.6}, {"rarity": "rare", "probability": 0.3}, {"rarity": "epic", "probability": 0.1},
            ],
        },
    )
    assert create_resp.status_code == 200
    pack_id = create_resp.json()["id"]
    assert len(create_resp.json()["rarity_probabilities"]) == 3

    update_resp = await client.put(f"/api/v1/admin/club-packs/{pack_id}", headers=auth, json={"price": 1500})
    assert update_resp.status_code == 200
    assert update_resp.json()["price"] == 1500

    toggle_resp = await client.post(f"/api/v1/admin/club-packs/{pack_id}/toggle-active", headers=auth)
    assert toggle_resp.json()["is_active"] is False

    list_resp = await client.get("/api/v1/admin/club-packs", headers=auth)
    assert any(p["id"] == pack_id for p in list_resp.json())

    delete_resp = await client.delete(f"/api/v1/admin/club-packs/{pack_id}", headers=auth)
    assert delete_resp.status_code == 204
