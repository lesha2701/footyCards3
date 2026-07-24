from tests.utils import telegram_headers


async def _admin_auth(client, bot_token):
    headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    session_resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


def _pack_payload(**overrides):
    payload = {
        "slug": "admin-test-pack",
        "name": "Admin Test Pack",
        "description": "",
        "price": 100,
        "card_count": 1,
        "guaranteed_min_rarity": None,
        "is_active": True,
        "image_path": None,
        "rarity_probabilities": [{"rarity": "common", "probability": 1.0}],
    }
    payload.update(overrides)
    return payload


async def test_create_pack(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    resp = await client.post("/api/v1/admin/packs", headers=auth, json=_pack_payload())
    assert resp.status_code == 200
    assert resp.json()["card_count"] == 1


async def test_update_pack_card_count_persists(client, db_session, bot_token):
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/packs", headers=auth, json=_pack_payload())
    pack_id = create_resp.json()["id"]

    update_payload = _pack_payload(card_count=2)
    del update_payload["slug"]
    update_resp = await client.put(f"/api/v1/admin/packs/{pack_id}", headers=auth, json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["card_count"] == 2

    list_resp = await client.get("/api/v1/admin/packs", headers=auth)
    updated = next(p for p in list_resp.json() if p["id"] == pack_id)
    assert updated["card_count"] == 2


async def test_update_pack_can_be_saved_twice_in_a_row(client, db_session, bot_token):
    # Regression: a stale rarity_probabilities collection made the second save fail.
    auth = await _admin_auth(client, bot_token)
    create_resp = await client.post("/api/v1/admin/packs", headers=auth, json=_pack_payload())
    pack_id = create_resp.json()["id"]

    update_payload = _pack_payload(card_count=2)
    del update_payload["slug"]
    first = await client.put(f"/api/v1/admin/packs/{pack_id}", headers=auth, json=update_payload)
    assert first.status_code == 200

    update_payload["card_count"] = 3
    second = await client.put(f"/api/v1/admin/packs/{pack_id}", headers=auth, json=update_payload)
    assert second.status_code == 200
    assert second.json()["card_count"] == 3
