from app.models.game import GameSession
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def test_saboteur_start_creates_session(client, db_session, bot_token):
    await _register(client, db_session, 820001, bot_token)
    headers = telegram_headers(820001, bot_token)

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["grid_size"] == 16
    assert body["bomb_count"] == 1


async def test_saboteur_reveal_never_leaks_bomb_index_on_safe_cell(client, db_session, bot_token):
    await _register(client, db_session, 820002, bot_token)
    headers = telegram_headers(820002, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]

    session = await db_session.get(GameSession, session_id)
    bomb_indices = session.server_state["bomb_indices"]
    safe_index = next(i for i in range(16) if i not in bomb_indices)

    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_bomb"] is False
    assert body["score"] == 8
    assert "bomb_indices" not in body


async def test_saboteur_hitting_bomb_halves_accumulated_score(client, db_session, bot_token):
    user = await _register(client, db_session, 820003, bot_token)
    headers = telegram_headers(820003, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]
    session = await db_session.get(GameSession, session_id)
    bomb_indices = session.server_state["bomb_indices"]

    safe_cells = [i for i in range(16) if i not in bomb_indices][:2]
    for cell in safe_cells:
        resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": cell})
        assert resp.status_code == 200

    bomb_index = bomb_indices[0]
    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": bomb_index})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_bomb"] is True
    assert body["status"] == "lost"
    assert body["reward_coins"] == 8  # 2 safe cells * 8 coins // 2 = 8

    claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 8

    await db_session.refresh(user)
    assert user.balance == 508


async def test_saboteur_voluntary_bank_awards_full_score(client, db_session, bot_token):
    await _register(client, db_session, 820004, bot_token)
    headers = telegram_headers(820004, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]
    session = await db_session.get(GameSession, session_id)
    bomb_indices = session.server_state["bomb_indices"]
    safe_cell = next(i for i in range(16) if i not in bomb_indices)

    await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_cell})
    end_resp = await client.post(f"/api/v1/games/saboteur/{session_id}/end", headers=headers)
    assert end_resp.status_code == 200
    assert end_resp.json()["reward_coins"] == 8

    claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 8

    second_claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_saboteur_higher_difficulty_multiplies_cell_reward(client, db_session, bot_token):
    await _register(client, db_session, 820006, bot_token)
    headers = telegram_headers(820006, bot_token)

    start = (
        await client.post("/api/v1/games/saboteur/start", headers=headers, json={"bomb_count": 3})
    ).json()
    assert start["bomb_count"] == 3
    session_id = start["session_id"]
    session = await db_session.get(GameSession, session_id)
    assert len(session.server_state["bomb_indices"]) == 3
    bomb_indices = session.server_state["bomb_indices"]
    safe_index = next(i for i in range(16) if i not in bomb_indices)

    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    assert resp.status_code == 200
    assert resp.json()["score"] == 24  # 8 base reward * 3 bombs


async def test_saboteur_bomb_count_out_of_range_is_rejected(client, db_session, bot_token):
    await _register(client, db_session, 820007, bot_token)
    headers = telegram_headers(820007, bot_token)

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers, json={"bomb_count": 0})
    assert resp.status_code == 409

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers, json={"bomb_count": 5})
    assert resp.status_code == 409


async def test_saboteur_hourly_limit_blocks_after_three_starts(client, db_session, bot_token):
    from datetime import timedelta

    await _register(client, db_session, 820005, bot_token)
    headers = telegram_headers(820005, bot_token)

    for _ in range(3):
        resp = await client.post("/api/v1/games/saboteur/start", headers=headers)
        assert resp.status_code == 200

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers)
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 3
    assert details["retry_after_seconds"] > 0

    user = await get_user_by_telegram_id(db_session, 820005)
    user.saboteur_hour_started_at = user.saboteur_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers)
    assert resp.status_code == 200
