import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    for position in Position:
        await create_player(db_session, position=position)


async def _create_club_and_join(client, bot_token, telegram_id, name):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _first_club_card_id(client, headers) -> int:
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert cards
    return cards[0]["id"]


async def test_shared_pool_lets_a_member_play_penalty_twice(client, bot_token):
    """The whole point of the shared pool: a member can spend both hourly
    slots on the SAME game (e.g. penalty twice) instead of being forced into
    exactly one of each — this was impossible under the old per-game limits."""
    _, headers = await _create_club_and_join(client, bot_token, 767001, "Общий пул клуб 1")
    card_id = await _first_club_card_id(client, headers)

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 200
    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 409


async def test_shared_pool_is_spent_across_different_club_games(client, bot_token):
    """Playing club_sequence once and then club_penalty once must exhaust the
    same shared pool — the two games are not independently limited."""
    _, headers = await _create_club_and_join(client, bot_token, 767002, "Общий пул клуб 2")
    card_id = await _first_club_card_id(client, headers)

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 200

    # Pool exhausted (2/2) — a third start of ANY club game is rejected.
    resp = await client.post("/api/v1/clubs/me/position-match/start", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["hourly_limit"] == 2

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 409


async def test_shared_pool_covers_all_three_club_games(client, bot_token):
    """One play on each of the three club games, in sequence, should exhaust
    a 2-slot pool by the second game and reject the third outright."""
    _, headers = await _create_club_and_join(client, bot_token, 767003, "Общий пул клуб 3")

    resp = await client.post("/api/v1/clubs/me/position-match/start", headers=headers)
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 200

    card_id = await _first_club_card_id(client, headers)
    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 409
