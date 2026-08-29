import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club creation — give every
    test in this file enough active players per formation category to draw from, mirroring
    test_club_game.py's identical fixture."""
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


async def test_missing_item_start_requires_club_membership(client, bot_token):
    headers = telegram_headers(760001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)
    assert resp.status_code == 404


async def test_missing_item_start_returns_five_distinct_items(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 760002, "Игровой клуб 1")

    resp = await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert len(body["items"]) == 5
    assert len(set(body["items"])) == 5  # all distinct


async def test_reveal_before_start_and_submit_before_reveal_are_rejected(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 760003, "Игровой клуб 2")

    start = (await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)).json()
    session_id = start["session_id"]

    submit_too_early = await client.post(
        f"/api/v1/clubs/me/missing-item/{session_id}/submit", headers=headers, json={"answer": start["items"][0]}
    )
    assert submit_too_early.status_code == 409


async def test_reveal_hides_one_item_and_keeps_it_secret(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 760004, "Игровой клуб 3")

    start = (await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)).json()
    session_id = start["session_id"]

    reveal = await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/reveal", headers=headers)
    assert reveal.status_code == 200
    body = reveal.json()
    assert len(body["items_shown"]) == 4
    assert set(body["items_shown"]).issubset(set(start["items"]))

    # Revealing the same round twice is rejected — one reveal per round.
    second_reveal = await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/reveal", headers=headers)
    assert second_reveal.status_code == 409


async def test_submit_correct_answer_advances_round_with_one_more_item(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 760005, "Игровой клуб 4")

    start = (await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)).json()
    session_id = start["session_id"]
    reveal = (await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/reveal", headers=headers)).json()

    missing = (set(start["items"]) - set(reveal["items_shown"])).pop()
    resp = await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/submit", headers=headers, json={"answer": missing})
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["score"] == 10
    assert body["next_round"]["round_number"] == 2
    assert len(body["next_round"]["items"]) == 6


async def test_submit_wrong_answer_ends_session(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 760006, "Игровой клуб 5")

    start = (await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)).json()
    session_id = start["session_id"]
    reveal = (await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/reveal", headers=headers)).json()

    missing = (set(start["items"]) - set(reveal["items_shown"])).pop()
    wrong_answer = next(i for i in start["items"] if i != missing)
    resp = await client.post(
        f"/api/v1/clubs/me/missing-item/{session_id}/submit", headers=headers, json={"answer": wrong_answer}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["status"] == "lost"


async def test_claim_credits_club_budget_not_player_coins(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    club, headers = await _create_club_and_join(client, bot_token, 760007, "Игровой клуб 6")
    user = await get_user_by_telegram_id(db_session, 760007)
    balance_before = user.balance
    budget_before = club["budget"]

    start = (await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)).json()
    session_id = start["session_id"]
    await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/reveal", headers=headers)
    submit = (
        await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/end", headers=headers)
    ).json()

    claim = await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    reward = claim.json()["reward_coins"]
    assert reward == submit["score"]
    assert claim.json()["new_club_budget"] == budget_before + reward

    await db_session.refresh(user)
    assert user.balance == balance_before  # reward goes to the club, never the player's own coins

    second_claim = await client.post(f"/api/v1/clubs/me/missing-item/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_hourly_limit_blocks_after_one_start(client, db_session, bot_token):
    from datetime import timedelta

    from tests.factories import get_user_by_telegram_id

    _, headers = await _create_club_and_join(client, bot_token, 760008, "Игровой клуб 7")

    resp = await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 1
    assert details["retry_after_seconds"] > 0

    user = await get_user_by_telegram_id(db_session, 760008)
    user.club_missing_item_hour_started_at = user.club_missing_item_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/clubs/me/missing-item/start", headers=headers)
    assert resp.status_code == 200
