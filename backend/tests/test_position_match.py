from app.models.enums import Position
from app.models.game import GameSession
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _seed_players(db_session):
    for position in Position:
        await create_player(db_session, position=position)


async def _start(client, db_session, telegram_id, bot_token):
    await _seed_players(db_session)
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post("/api/v1/games/position-match/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    session = await db_session.get(GameSession, body["session_id"])
    return headers, body, session


async def test_position_match_start_deals_five_distinct_positions(client, db_session, bot_token):
    _headers, body, session = await _start(client, db_session, 760001, bot_token)

    assert len(body["cards"]) == 5
    assert len(body["positions"]) == 5
    # The card payload deliberately omits the answer.
    assert "position" not in body["cards"][0]

    positions_by_card_id = session.server_state["positions_by_card_id"]
    assert len(set(positions_by_card_id.values())) == 5
    assert set(body["positions"]) == set(positions_by_card_id.values())


async def test_position_match_correct_and_wrong_attempts(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760002, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_ids = [c["id"] for c in body["cards"]]

    correct_id = card_ids[0]
    correct_position = positions_by_card_id[str(correct_id)]
    resp = await client.post(
        f"/api/v1/games/position-match/{session.id}/match",
        headers=headers, json={"player_id": correct_id, "position": correct_position},
    )
    assert resp.status_code == 200
    match_body = resp.json()
    assert match_body["correct"] is True
    assert match_body["matched_player_ids"] == [correct_id]
    assert match_body["mistakes"] == 0

    wrong_id = card_ids[1]
    wrong_position = next(p for p in positions_by_card_id.values() if p != positions_by_card_id[str(wrong_id)])
    resp = await client.post(
        f"/api/v1/games/position-match/{session.id}/match",
        headers=headers, json={"player_id": wrong_id, "position": wrong_position},
    )
    assert resp.status_code == 200
    wrong_body = resp.json()
    assert wrong_body["correct"] is False
    assert wrong_body["mistakes"] == 1
    assert wrong_id not in wrong_body["matched_player_ids"]


async def test_position_match_wins_with_zero_mistakes_and_pays_full_reward(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760003, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]

    status = None
    for card in body["cards"]:
        resp = await client.post(
            f"/api/v1/games/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )
        status = resp.json()["status"]
    assert status == "won"

    claim = await client.post(f"/api/v1/games/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 35  # position_match_reward_perfect default, 0 mistakes

    second_claim = await client.post(f"/api/v1/games/position-match/{session.id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_position_match_reward_drops_linearly_per_mistake(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760004, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_ids = [c["id"] for c in body["cards"]]

    # Two wrong attempts first (reused against the same card — matching a
    # not-yet-matched card to a position that isn't its own is always
    # rejected and always counts as a mistake, regardless of which card
    # eventually "owns" that position).
    wrong_position = next(p for p in positions_by_card_id.values() if p != positions_by_card_id[str(card_ids[0])])
    for _ in range(2):
        await client.post(
            f"/api/v1/games/position-match/{session.id}/match",
            headers=headers, json={"player_id": card_ids[0], "position": wrong_position},
        )

    for card in body["cards"]:
        await client.post(
            f"/api/v1/games/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )

    claim = await client.post(f"/api/v1/games/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 35 - 2 * 8  # perfect - mistakes * penalty


async def test_position_match_loses_after_max_mistakes(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760005, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_ids = [c["id"] for c in body["cards"]]
    wrong_position = next(p for p in positions_by_card_id.values() if p != positions_by_card_id[str(card_ids[0])])

    status = None
    for _ in range(3):  # position_match_max_mistakes default
        resp = await client.post(
            f"/api/v1/games/position-match/{session.id}/match",
            headers=headers, json={"player_id": card_ids[0], "position": wrong_position},
        )
        status = resp.json()["status"]
    assert status == "lost"

    claim = await client.post(f"/api/v1/games/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0


async def test_position_match_rejects_matching_an_already_matched_card(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760006, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]
    card_id = body["cards"][0]["id"]
    correct_position = positions_by_card_id[str(card_id)]

    await client.post(
        f"/api/v1/games/position-match/{session.id}/match",
        headers=headers, json={"player_id": card_id, "position": correct_position},
    )
    resp = await client.post(
        f"/api/v1/games/position-match/{session.id}/match",
        headers=headers, json={"player_id": card_id, "position": correct_position},
    )
    assert resp.status_code == 409


async def test_position_match_rejects_card_not_in_this_round(client, db_session, bot_token):
    headers, body, session = await _start(client, db_session, 760007, bot_token)
    used_ids = {c["id"] for c in body["cards"]}
    other_player = await create_player(db_session, position=Position.GK)
    assert other_player.id not in used_ids

    resp = await client.post(
        f"/api/v1/games/position-match/{session.id}/match",
        headers=headers, json={"player_id": other_player.id, "position": "GK"},
    )
    assert resp.status_code == 409


async def test_position_match_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config

    headers, body, session = await _start(client, db_session, 760008, bot_token)
    positions_by_card_id = session.server_state["positions_by_card_id"]

    user = await get_user_by_telegram_id(db_session, 760008)
    config = await get_config(db_session)
    user.position_match_rewarded_attempts_today = config.position_match_daily_limit
    user.position_match_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    for card in body["cards"]:
        await client.post(
            f"/api/v1/games/position-match/{session.id}/match",
            headers=headers, json={"player_id": card["id"], "position": positions_by_card_id[str(card["id"])]},
        )

    claim = await client.post(f"/api/v1/games/position-match/{session.id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0

    await db_session.refresh(user)
    assert user.position_match_rewarded_attempts_today == config.position_match_daily_limit
