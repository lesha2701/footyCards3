from tests.utils import telegram_headers


async def test_memory_start_returns_sequence(client, bot_token):
    headers = telegram_headers(740001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/games/memory/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert len(body["sequence"]) == 3


async def test_memory_submit_correct_answer_advances_round(client, bot_token):
    headers = telegram_headers(740002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/memory/start", headers=headers)).json()
    session_id = start["session_id"]

    resp = await client.post(
        f"/api/v1/games/memory/{session_id}/submit", headers=headers, json={"answer": start["sequence"]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["next_round"]["round_number"] == 2
    assert body["score"] == 10


async def test_memory_submit_wrong_answer_ends_session(client, bot_token):
    headers = telegram_headers(740003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/memory/start", headers=headers)).json()
    session_id = start["session_id"]

    wrong_answer = ["🚫", "🚫", "🚫"]
    resp = await client.post(
        f"/api/v1/games/memory/{session_id}/submit", headers=headers, json={"answer": wrong_answer}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["status"] == "lost"


async def test_memory_claim_reward_credits_coins_once(client, bot_token):
    headers = telegram_headers(740004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/memory/start", headers=headers)).json()
    session_id = start["session_id"]
    await client.post(f"/api/v1/games/memory/{session_id}/submit", headers=headers, json={"answer": ["🚫"]})

    first_claim = await client.post(f"/api/v1/games/memory/{session_id}/claim", headers=headers)
    assert first_claim.status_code == 200
    assert first_claim.json()["reward_coins"] == 0  # session ended on round 1 without a correct answer -> score 0

    second_claim = await client.post(f"/api/v1/games/memory/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409
