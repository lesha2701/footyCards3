from app.models.coach import Coach
from app.models.user_coach_card import UserCoachCard
from tests.factories import get_user_by_telegram_id
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


async def test_update_coach_rarity_only_to_diamond_returns_clean_conflict(client, db_session, bot_token):
    # Regression: a rarity-only PUT to "diamond" used to sail past the
    # schema layer (which had no boosts to validate against) and hit the
    # DB's ck_coaches_rarity_not_diamond CheckConstraint as a raw
    # IntegrityError, surfacing as an unhandled 500. It must now come back
    # as a clean ConflictError response (409), not a 500.
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={
            "display_name": "Diamond Hopeful", "rarity": "legendary", "quick_sell_price": 50,
            "boosts": [
                {"boost_type": "attack_central", "magnitude": 6.0},
                {"boost_type": "defence_central", "magnitude": 6.0},
                {"boost_type": "goalkeeping", "magnitude": 4.0},
            ],
        },
    )
    coach_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/admin/coaches/{coach_id}", headers=auth, json={"rarity": "diamond"},
    )
    assert update_resp.status_code == 409, update_resp.text
    assert update_resp.json()["error"]["code"] == "conflict"


async def test_update_coach_rarity_only_leaving_mismatched_boosts_rejected(client, db_session, bot_token):
    # Rarity-only PUT that drops a legendary (3-boost) coach to common
    # (1-boost) must be rejected rather than leaving an inconsistent row.
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={
            "display_name": "Downgrade Candidate", "rarity": "legendary", "quick_sell_price": 50,
            "boosts": [
                {"boost_type": "attack_central", "magnitude": 6.0},
                {"boost_type": "defence_central", "magnitude": 6.0},
                {"boost_type": "goalkeeping", "magnitude": 4.0},
            ],
        },
    )
    coach_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/admin/coaches/{coach_id}", headers=auth, json={"rarity": "common"},
    )
    assert update_resp.status_code == 409, update_resp.text

    # The coach must be left completely untouched by the rejected update.
    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    coach = next(c for c in list_resp.json()["items"] if c["id"] == coach_id)
    assert coach["rarity"] == "legendary"
    assert len(coach["boosts"]) == 3


async def test_update_coach_boosts_only_leaving_mismatched_count_rejected(client, db_session, bot_token):
    # Boosts-only PUT that would leave a legendary coach with only 1 boost
    # (needs 3) must be rejected.
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={
            "display_name": "Under-boost Candidate", "rarity": "legendary", "quick_sell_price": 50,
            "boosts": [
                {"boost_type": "attack_central", "magnitude": 6.0},
                {"boost_type": "defence_central", "magnitude": 6.0},
                {"boost_type": "goalkeeping", "magnitude": 4.0},
            ],
        },
    )
    coach_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/admin/coaches/{coach_id}", headers=auth,
        json={"boosts": [{"boost_type": "attack_central", "magnitude": 6.0}]},
    )
    assert update_resp.status_code == 409, update_resp.text


async def test_toggle_active_and_delete_coach(client, db_session, bot_token):
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={"display_name": "Togglable Coach", "rarity": "common", "boosts": [{"boost_type": "ball_control", "magnitude": 0.1}]},
    )
    coach_id = create_resp.json()["id"]

    toggle_resp = await client.post(f"/api/v1/admin/coaches/{coach_id}/toggle-active", headers=auth)
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["is_active"] is False

    delete_resp = await client.delete(f"/api/v1/admin/coaches/{coach_id}", headers=auth)
    assert delete_resp.status_code == 200

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    assert all(c["id"] != coach_id for c in list_resp.json()["items"])


async def test_delete_coach_with_owned_user_card_returns_conflict_not_500(client, db_session, bot_token):
    # Regression: UserCoachCard/ClubCoachCard reference coaches.id with no
    # ON DELETE clause, so deleting an owned coach used to raise an
    # unhandled IntegrityError (bare 500) — and delete_coach_image() ran
    # before that failing delete, orphaning the image file. Deleting a
    # coach with owned copies must now come back as a clean 409 and leave
    # the coach row (and its image) untouched.
    token = await _admin_token(client, bot_token)
    auth = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/admin/coaches", headers=auth,
        json={"display_name": "Owned Coach", "rarity": "common", "boosts": [{"boost_type": "ball_control", "magnitude": 0.1}]},
    )
    assert create_resp.status_code == 200, create_resp.text
    coach_id = create_resp.json()["id"]

    headers = telegram_headers(840300, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 840300)

    coach = await db_session.get(Coach, coach_id)
    db_session.add(UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source="pack"))
    await db_session.commit()

    delete_resp = await client.delete(f"/api/v1/admin/coaches/{coach_id}", headers=auth)
    assert delete_resp.status_code == 409, delete_resp.text
    assert delete_resp.json()["error"]["code"] == "conflict"

    list_resp = await client.get("/api/v1/admin/coaches", headers=auth)
    surviving = next((c for c in list_resp.json()["items"] if c["id"] == coach_id), None)
    assert surviving is not None
    assert surviving["display_name"] == "Owned Coach"
