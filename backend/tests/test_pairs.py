from tests.factories import create_player
from tests.utils import telegram_headers


async def _seed_players(db_session, count=12):
    for _ in range(count):
        await create_player(db_session)


async def test_pairs_start_deals_a_25_cell_board(client, db_session, bot_token):
    await _seed_players(db_session)
    headers = telegram_headers(750001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/games/pairs/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["board_size"] == 25
    assert body["total_pairs"] == 12


async def test_pairs_mismatched_flip_counts_as_wrong_attempt(client, db_session, bot_token):
    from app.models.game import GameSession

    await _seed_players(db_session)
    headers = telegram_headers(750002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/pairs/start", headers=headers)).json()
    session_id = start["session_id"]

    session = await db_session.get(GameSession, session_id)
    board = session.server_state["board"]
    non_bonus = [i for i, v in enumerate(board) if v is not None]
    a = non_bonus[0]
    b = next(i for i in non_bonus if board[i] != board[a])

    await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": a})
    resp = await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": b})
    assert resp.status_code == 200
    body = resp.json()
    assert body["matched"] is False
    assert body["wrong_attempts"] == 1


async def test_pairs_wins_only_after_bonus_tile_is_found(client, db_session, bot_token):
    """Regression test: matching all 12 pairs must not end the session while
    the 25th (bonus) tile is still face-down — otherwise a player who leaves
    the bonus for last can never reach it."""
    from app.models.game import GameSession

    await _seed_players(db_session)
    headers = telegram_headers(750003, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/pairs/start", headers=headers)).json()
    session_id = start["session_id"]

    session = await db_session.get(GameSession, session_id)
    board = session.server_state["board"]

    positions_by_value: dict[int, list[int]] = {}
    bonus_pos = None
    for i, v in enumerate(board):
        if v is None:
            bonus_pos = i
        else:
            positions_by_value.setdefault(v, []).append(i)

    last_status = None
    for a, b in positions_by_value.values():
        await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": a})
        resp = await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": b})
        last_status = resp.json()["status"]

    assert last_status == "in_progress"

    resp = await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": bonus_pos})
    body = resp.json()
    assert body["status"] == "won"
    assert body["matched"] is True

    claim = await client.post(f"/api/v1/games/pairs/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    # Perfect run (0 wrong attempts) + bonus tile found.
    assert claim.json()["reward_coins"] == 60 + 25

    second_claim = await client.post(f"/api/v1/games/pairs/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_pairs_rejects_flipping_the_same_position_twice(client, db_session, bot_token):
    await _seed_players(db_session)
    headers = telegram_headers(750004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    start = (await client.post("/api/v1/games/pairs/start", headers=headers)).json()
    session_id = start["session_id"]

    await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": 0})
    resp = await client.post(f"/api/v1/games/pairs/{session_id}/flip", headers=headers, json={"position": 0})
    assert resp.status_code == 409
