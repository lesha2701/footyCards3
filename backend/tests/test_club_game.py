import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club creation — give every
    test in this file enough active players per formation category to draw from, mirroring
    test_clubs.py's identical fixture (see its docstring for the full rationale)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
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


async def test_club_game_start_requires_club_membership(client, bot_token):
    headers = telegram_headers(750001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 404


async def test_club_game_start_returns_sequence_and_icons(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 750002, "Игровой клуб 1")

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert len(body["sequence"]) == 3
    assert len(body["icons"]) == 5
    assert all(s in body["icons"] for s in body["sequence"])


async def test_club_game_submit_correct_answer_advances_round(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 750003, "Игровой клуб 2")

    start = (await client.post("/api/v1/clubs/me/game/start", headers=headers)).json()
    session_id = start["session_id"]

    resp = await client.post(
        f"/api/v1/clubs/me/game/{session_id}/submit", headers=headers, json={"answer": start["sequence"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["next_round"]["round_number"] == 2
    assert body["score"] == 10


async def test_club_game_submit_wrong_answer_ends_session(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 750004, "Игровой клуб 3")

    start = (await client.post("/api/v1/clubs/me/game/start", headers=headers)).json()
    session_id = start["session_id"]

    resp = await client.post(
        f"/api/v1/clubs/me/game/{session_id}/submit", headers=headers, json={"answer": ["🚫", "🚫", "🚫"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["status"] == "lost"


async def test_club_game_claim_credits_club_budget_not_player_coins(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    club, headers = await _create_club_and_join(client, bot_token, 750005, "Игровой клуб 4")
    user = await get_user_by_telegram_id(db_session, 750005)
    balance_before = user.balance
    budget_before = club["budget"]

    start = (await client.post("/api/v1/clubs/me/game/start", headers=headers)).json()
    session_id = start["session_id"]
    submit = (
        await client.post(
            f"/api/v1/clubs/me/game/{session_id}/submit", headers=headers, json={"answer": start["sequence"]}
        )
    ).json()
    await client.post(f"/api/v1/clubs/me/game/{session_id}/end", headers=headers)

    claim = await client.post(f"/api/v1/clubs/me/game/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    reward = claim.json()["reward_coins"]
    assert reward == submit["score"]
    assert claim.json()["new_club_budget"] == budget_before + reward

    await db_session.refresh(user)
    assert user.balance == balance_before  # reward goes to the club, never the player's own coins

    second_claim = await client.post(f"/api/v1/clubs/me/game/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_club_game_hourly_limit_blocks_after_one_start(client, db_session, bot_token):
    from datetime import timedelta

    from tests.factories import get_user_by_telegram_id

    _, headers = await _create_club_and_join(client, bot_token, 750006, "Игровой клуб 5")

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 1
    assert details["retry_after_seconds"] > 0

    user = await get_user_by_telegram_id(db_session, 750006)
    user.club_game_hour_started_at = user.club_game_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert resp.status_code == 200


async def test_club_game_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config
    from tests.factories import get_user_by_telegram_id

    _club, headers = await _create_club_and_join(client, bot_token, 750007, "Игровой клуб 6")
    user = await get_user_by_telegram_id(db_session, 750007)

    config = await get_config(db_session)
    daily_limit = config.club_game_daily_reward_limit
    user.club_game_rewarded_attempts_today = daily_limit
    user.club_game_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    start = await client.post("/api/v1/clubs/me/game/start", headers=headers)
    assert start.status_code == 200
    session_id = start.json()["session_id"]
    await client.post(f"/api/v1/clubs/me/game/{session_id}/submit", headers=headers, json={"answer": ["🚫"]})

    claim = await client.post(f"/api/v1/clubs/me/game/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0
    assert claim.json()["daily_cap_reached"] is True

    await db_session.refresh(user)
    assert user.club_game_rewarded_attempts_today == daily_limit
