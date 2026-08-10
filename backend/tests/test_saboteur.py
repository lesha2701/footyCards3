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
    assert body["line_size"] == 5
    assert body["steward_count"] == 1
    assert body["level"] == 1


async def test_saboteur_reveal_never_leaks_steward_index_on_safe_cell(client, db_session, bot_token):
    await _register(client, db_session, 820002, bot_token)
    headers = telegram_headers(820002, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]

    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_index = next(i for i in range(5) if i not in line_stewards)

    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_steward"] is False
    assert body["score"] == 8  # base_reward(8) * steward_count(1) * growth^0
    assert body["level"] == 2
    assert "line_stewards" not in body


async def test_saboteur_hitting_steward_pays_flat_one_line_consolation(client, db_session, bot_token):
    user = await _register(client, db_session, 820003, bot_token)
    headers = telegram_headers(820003, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]

    # Clear a couple of lines first so the accumulated score is well above
    # the one-line consolation payout, to prove the payout doesn't scale
    # with progress.
    for _ in range(2):
        db_session.expire_all()
        session = await db_session.get(GameSession, session_id)
        line_stewards = session.server_state["line_stewards"]
        safe_index = next(i for i in range(5) if i not in line_stewards)
        resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
        assert resp.status_code == 200

    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    assert session.score > 8  # more than one line's worth already banked in-progress
    steward_index = session.server_state["line_stewards"][0]

    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": steward_index})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_steward"] is True
    assert body["status"] == "lost"
    assert body["reward_coins"] == 8  # flat one-line consolation, not proportional to progress

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
    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_cell = next(i for i in range(5) if i not in line_stewards)

    await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_cell})
    end_resp = await client.post(f"/api/v1/games/saboteur/{session_id}/end", headers=headers)
    assert end_resp.status_code == 200
    assert end_resp.json()["reward_coins"] == 8

    claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 8

    second_claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_saboteur_higher_difficulty_multiplies_line_reward(client, db_session, bot_token):
    await _register(client, db_session, 820006, bot_token)
    headers = telegram_headers(820006, bot_token)

    start = (
        await client.post("/api/v1/games/saboteur/start", headers=headers, json={"steward_count": 3})
    ).json()
    assert start["steward_count"] == 3
    session_id = start["session_id"]
    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    assert len(session.server_state["line_stewards"]) == 3
    line_stewards = session.server_state["line_stewards"]
    safe_index = next(i for i in range(5) if i not in line_stewards)

    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    assert resp.status_code == 200
    assert resp.json()["score"] == 24  # 8 base reward * 3 stewards * growth^0


async def test_saboteur_reward_escalates_with_ladder_level(client, db_session, bot_token):
    await _register(client, db_session, 820008, bot_token)
    headers = telegram_headers(820008, bot_token)

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]

    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_index = next(i for i in range(5) if i not in line_stewards)
    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    level1_gain = resp.json()["score"]

    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_index = next(i for i in range(5) if i not in line_stewards)
    resp = await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index})
    level2_gain = resp.json()["score"] - level1_gain

    assert level2_gain > level1_gain  # each cleared line is worth more than the last


async def test_saboteur_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config

    user = await _register(client, db_session, 820007, bot_token)
    headers = telegram_headers(820007, bot_token)

    config = await get_config(db_session)
    daily_limit = config.saboteur_daily_limit
    user.saboteur_rewarded_attempts_today = daily_limit
    user.saboteur_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    start_resp = await client.post("/api/v1/games/saboteur/start", headers=headers)
    assert start_resp.status_code == 200
    start = start_resp.json()
    session_id = start["session_id"]
    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_cell = next(i for i in range(5) if i not in line_stewards)

    await client.post(f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_cell})
    await client.post(f"/api/v1/games/saboteur/{session_id}/end", headers=headers)

    claim = await client.post(f"/api/v1/games/saboteur/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0

    await db_session.refresh(user)
    assert user.saboteur_rewarded_attempts_today == daily_limit


async def test_saboteur_steward_count_out_of_range_is_rejected(client, db_session, bot_token):
    await _register(client, db_session, 820007, bot_token)
    headers = telegram_headers(820007, bot_token)

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers, json={"steward_count": 0})
    assert resp.status_code == 409

    resp = await client.post("/api/v1/games/saboteur/start", headers=headers, json={"steward_count": 5})
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
