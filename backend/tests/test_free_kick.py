from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.services.free_kick_service import half_width_for_rating
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _grant_card(db_session, owner_id: int, rating: int = 80) -> UserCard:
    player = await create_player(db_session, rarity=Rarity.rare, rating=rating)
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.flush()
    card.serial_number = card.id
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


def test_half_width_grows_with_rating():
    assert half_width_for_rating(99) > half_width_for_rating(58)
    assert round(half_width_for_rating(58), 1) == 4.0
    assert round(half_width_for_rating(99), 1) == 12.0


async def test_free_kick_perfect_hit_at_elapsed_zero(client, db_session, bot_token):
    user = await _register(client, db_session, 840001, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(840001, bot_token)

    start = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200

    session_id = start.json()["session_id"]
    resp = await client.post(f"/api/v1/games/free-kick/{session_id}/kick", headers=headers, json={"elapsed_ms": 0})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "perfect"
    assert body["coins_this_kick"] > 0
    assert body["is_finished"] is False
    assert body["next_kick"]["kick_index"] == 1


async def test_free_kick_rejects_fabricated_elapsed_ms_sent_without_waiting(client, db_session, bot_token):
    # A tampered client can read `period_ms` from the start response and
    # compute the exact elapsed_ms that lands on the sine wave's center
    # (a guaranteed "perfect" hit) without ever actually waiting for real
    # time to pass. The server must clamp elapsed_ms to what it actually
    # observed, so submitting this instantly must NOT yield "perfect".
    user = await _register(client, db_session, 840006, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(840006, bot_token)

    start = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]
    period_ms = start.json()["kick"]["period_ms"]

    fabricated_elapsed_ms = period_ms // 2  # would be an exact "perfect" hit if trusted verbatim
    resp = await client.post(
        f"/api/v1/games/free-kick/{session_id}/kick", headers=headers, json={"elapsed_ms": fabricated_elapsed_ms}
    )
    assert resp.status_code == 200
    assert resp.json()["tier"] != "perfect"


async def test_free_kick_completes_after_three_kicks_and_pays_claim(client, db_session, bot_token):
    user = await _register(client, db_session, 840002, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(840002, bot_token)

    start = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]

    total = 0
    for i in range(3):
        resp = await client.post(f"/api/v1/games/free-kick/{session_id}/kick", headers=headers, json={"elapsed_ms": 0})
        assert resp.status_code == 200
        body = resp.json()
        total = body["total_coins"]
        assert body["is_finished"] == (i == 2)

    claim = await client.post(f"/api/v1/games/free-kick/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == total

    await db_session.refresh(user)
    assert user.balance == 500 + total


async def test_free_kick_start_rejects_card_not_owned(client, db_session, bot_token):
    await _register(client, db_session, 840003, bot_token)
    other_user = await _register(client, db_session, 840004, bot_token)
    other_card = await _grant_card(db_session, other_user.id)

    headers = telegram_headers(840003, bot_token)
    resp = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": other_card.id})
    assert resp.status_code == 403


async def test_free_kick_hourly_limit_blocks_after_three_starts(client, db_session, bot_token):
    from datetime import timedelta

    user = await _register(client, db_session, 840005, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(840005, bot_token)

    for _ in range(3):
        resp = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
        assert resp.status_code == 200

    resp = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 3
    assert details["retry_after_seconds"] > 0

    await db_session.refresh(user)
    user.free_kick_hour_started_at = user.free_kick_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/games/free-kick/start", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 200
