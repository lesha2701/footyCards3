import pytest_asyncio

from app.models.enums import Position
from app.models.game import GameSession
from tests.factories import create_player, get_user_by_telegram_id
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


async def _start(client, db_session, telegram_id, bot_token, name):
    await _create_club_and_join(client, bot_token, telegram_id, name)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post("/api/v1/clubs/me/position-match/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    session = await db_session.get(GameSession, body["session_id"])
    return headers, body, session


async def test_club_position_match_requires_membership(client, bot_token):
    headers = telegram_headers(766001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/clubs/me/position-match/start", headers=headers)
    assert resp.status_code == 404


async def test_club_position_match_start_deals_five_distinct_positions(client, db_session, bot_token):
    _headers, body, session = await _start(client, db_session, 766002, bot_token, "Позиционный клуб 1")

    assert len(body["cards"]) == 5
    assert len(body["positions"]) == 5
    assert "position" not in body["cards"][0]

    positions_by_card_id = session.server_state["positions_by_card_id"]
    assert len(set(positions_by_card_id.values())) == 5
    assert session.server_state["club_id"] is not None


async def test_club_position_match_wins_and_credits_club_budget_not_player_coins(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 766003, bot_token, "Позиционный клуб 2")
    positions_by_card_id = session.server_state["positions_by_card_id"]

    user = await get_user_by_telegram_id(db_session, 766003)
    balance_before = user.balance

    status = None
    for card in body["cards"]:
        resp = await client.post(
            f"/api/v1/clubs/me/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )
        status = resp.json()["status"]
    assert status == "won"

    from app.models.club import Club
    club = await db_session.get(Club, session.server_state["club_id"])
    budget_before = club.budget

    claim = await client.post(f"/api/v1/clubs/me/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    body = claim.json()
    assert body["reward_coins"] == 35  # club_position_match_reward_perfect default, 0 mistakes
    assert body["new_club_budget"] == budget_before + 35

    await db_session.refresh(user)
    assert user.balance == balance_before  # reward goes to the club, never the player's own coins

    second_claim = await client.post(f"/api/v1/clubs/me/position-match/{session.id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_club_position_match_reward_drops_linearly_per_mistake(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 766004, bot_token, "Позиционный клуб 3")
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_ids = [c["id"] for c in body["cards"]]

    wrong_position = next(p for p in positions_by_card_id.values() if p != positions_by_card_id[str(card_ids[0])])
    for _ in range(2):
        await client.post(
            f"/api/v1/clubs/me/position-match/{session.id}/match",
            headers=headers, json={"player_id": card_ids[0], "position": wrong_position},
        )

    for card in body["cards"]:
        await client.post(
            f"/api/v1/clubs/me/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )

    claim = await client.post(f"/api/v1/clubs/me/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 35 - 2 * 8  # perfect - mistakes * penalty


async def test_club_position_match_loses_after_max_mistakes(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 766005, bot_token, "Позиционный клуб 4")
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_ids = [c["id"] for c in body["cards"]]
    wrong_position = next(p for p in positions_by_card_id.values() if p != positions_by_card_id[str(card_ids[0])])

    status = None
    for _ in range(3):  # club_position_match_max_mistakes default
        resp = await client.post(
            f"/api/v1/clubs/me/position-match/{session.id}/match",
            headers=headers, json={"player_id": card_ids[0], "position": wrong_position},
        )
        status = resp.json()["status"]
    assert status == "lost"

    claim = await client.post(f"/api/v1/clubs/me/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0


async def test_club_position_match_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config

    headers, body, session = await _start(client, db_session, 766006, bot_token, "Позиционный клуб 5")
    positions_by_card_id = session.server_state["positions_by_card_id"]

    user = await get_user_by_telegram_id(db_session, 766006)
    config = await get_config(db_session)
    user.club_position_match_rewarded_attempts_today = config.club_position_match_daily_reward_limit
    user.club_position_match_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    for card in body["cards"]:
        await client.post(
            f"/api/v1/clubs/me/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )

    claim = await client.post(f"/api/v1/clubs/me/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0
    assert claim.json()["daily_cap_reached"] is True
