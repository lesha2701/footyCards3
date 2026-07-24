from app.models.enums import CardSource
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _build_full_squad(db_session, user_id: int) -> list[dict]:
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    return slots


async def test_set_lineup_success(client, db_session, bot_token):
    headers = telegram_headers(750001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750001)

    slots = await _build_full_squad(db_session, user.id)
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] > 0


async def test_cannot_use_other_users_card_in_lineup(client, db_session, bot_token):
    headers = telegram_headers(750002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    owner, _ = None, None

    other_headers = telegram_headers(750003, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other_user = await get_user_by_telegram_id(db_session, 750003)

    player = await create_player(db_session, position=FORMATION_SLOTS[0].ideal_position)
    other_card = await create_user_card(db_session, other_user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.put(
        "/api/v1/lineups/active", headers=headers,
        json={"slots": [{"slot_code": FORMATION_SLOTS[0].code, "user_card_id": other_card.id}]},
    )
    assert resp.status_code == 403


async def test_play_match_requires_complete_lineup(client, bot_token):
    headers = telegram_headers(750004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409


async def test_play_match_with_complete_lineup(client, db_session, bot_token):
    headers = telegram_headers(750005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750005)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"] in ("win", "draw", "loss")
    assert len(body["events"]) > 0

    await db_session.refresh(user)
    assert user.match_energy == 9


async def test_match_hourly_limit_blocks_after_three_plays(client, db_session, bot_token):
    headers = telegram_headers(750006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750006)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    for _ in range(3):
        resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
        assert resp.status_code == 200

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 3
    assert details["retry_after_seconds"] > 0

    await db_session.refresh(user)
    from datetime import timedelta

    user.match_hour_started_at = user.match_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
