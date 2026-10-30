from datetime import date

import pytest

import app.core.rate_limit as rate_limit_module
from app.services import free_kick_3d_engine as engine
from app.services.free_kick_challenge_service import day_kicks, score_kick
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _register
from tests.test_free_kick_3d import SWIPE, _age_current_kick
from tests.utils import telegram_headers

API = "/api/v1/games/free-kick-3d/challenge"


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


def _result(outcome, x, y):
    return engine.ShotResult(outcome, 1.0, (x, y, -0.12), (0, 0, -20), (0, 0, 0), [outcome])


def test_the_day_sets_the_positions_and_targets():
    day = date(2026, 10, 30)
    assert day_kicks(day, 5) == day_kicks(day, 5)
    assert day_kicks(day, 5) != day_kicks(date(2026, 10, 31), 5)
    for k in day_kicks(day, 5):
        assert abs(k["x"]) + k["r"] <= engine.GOAL_HALF_WIDTH and k["y"] + k["r"] <= engine.GOAL_HEIGHT + 0.01


def test_points_by_closeness_inside_the_target():
    target = {"x": 2.0, "y": 1.0, "r": 0.5}
    assert score_kick(_result("goal", 2.0, 1.0), target) == (100, True)
    assert score_kick(_result("goal", 2.25, 1.0), target) == (75, True)
    assert score_kick(_result("goal", -2.0, 1.0), target) == (10, False)
    assert score_kick(_result("save", 2.0, 1.0), target) == (0, False)


async def test_one_attempt_a_day_replayed_paid_once_and_ranked(client, db_session, bot_token):
    user = await _register(client, db_session, 851001, bot_token)
    headers = telegram_headers(851001, bot_token)
    config = await get_config(db_session)

    before = (await client.get(API, headers=headers)).json()
    assert before["my"] is None and before["total_kicks"] == config.free_kick_challenge_kicks

    start = (await client.post(f"{API}/start", headers=headers)).json()
    sid = start["session_id"]
    assert len(start["targets"]) == start["total_kicks"] == 5
    assert start["rating"] == config.free_kick_challenge_rating
    # Picking it up again (an app closed mid-way) returns the same attempt.
    again = (await client.post(f"{API}/start", headers=headers)).json()
    assert again["session_id"] == sid and again["kick"] == start["kick"]

    too_fast = await client.post(f"{API}/{sid}/shot", headers=headers, json=SWIPE)
    assert too_fast.status_code == 409

    score = hits = 0
    body = None
    for i in range(5):
        kick = await _age_current_kick(db_session, sid)
        resp = await client.post(f"{API}/{sid}/shot", headers=headers, json=SWIPE)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        replay = engine.simulate_shot(
            engine.create_setup(kick["seed"], config.free_kick_challenge_rating),
            engine.Swipe(SWIPE["dx"], SWIPE["dy"], SWIPE["curve"], SWIPE["duration_ms"]),
        )
        points, hit = score_kick(replay, kick)
        score += points
        hits += hit
        assert (body["outcome"], body["points"], body["hit"], body["score"]) == (replay.outcome, points, hit, score)
        assert body["is_finished"] is (i == 4)

    reward = hits * config.free_kick_challenge_coins_per_hit + (config.free_kick_challenge_perfect_bonus if hits == 5 else 0)
    assert body["reward_coins"] == reward and body["rank"] == 1
    assert (await get_user_by_telegram_id(db_session, 851001)).balance == body["new_balance"]

    assert (await client.post(f"{API}/start", headers=headers)).status_code == 409
    assert (await client.post(f"/api/v1/games/free-kick/{sid}/claim", headers=headers)).status_code == 409

    # A second player who leaves after one kick still shows on the board.
    await _register(client, db_session, 851002, bot_token)
    other = telegram_headers(851002, bot_token)
    sid2 = (await client.post(f"{API}/start", headers=other)).json()["session_id"]
    await _age_current_kick(db_session, sid2)
    await client.post(f"{API}/{sid2}/shot", headers=other, json=SWIPE)
    board = (await client.get(API, headers=other)).json()
    assert board["players"] == 2
    assert board["my"]["finished"] is False
    assert [r["is_me"] for r in board["top"]].count(True) == 1
    assert board["top"][0]["score"] >= board["top"][1]["score"]
    assert user.id
