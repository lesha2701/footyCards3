from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.orm.attributes import flag_modified

from app.models.game import GameSession
from app.services import free_kick_3d_engine as engine
from app.services.free_kick_service import score_3d_shot
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _grant_card, _register
from tests.utils import telegram_headers

SWIPE = {"dx": 50, "dy": -300, "curve": 40, "duration_ms": 180}


async def _age_current_kick(db_session, session_id: int, seconds: float = 2) -> dict:
    """Pretend the player took their time over the current position."""
    session = await db_session.get(GameSession, session_id)
    await db_session.refresh(session)
    state = dict(session.server_state)
    kicks = [dict(k) for k in state["kicks"]]
    idx = state["current_kick_index"]
    kicks[idx]["issued_at"] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    state["kicks"] = kicks
    session.server_state = state
    flag_modified(session, "server_state")
    db_session.add(session)
    await db_session.commit()
    return kicks[idx]


def _config(**over):
    base = dict(free_kick_3d_goal_coins=20, free_kick_3d_corner_bonus=10, free_kick_3d_curl_bonus=5, free_kick_3d_near_coins=3)
    return SimpleNamespace(**{**base, **over})


def _result(outcome, x=0.0, y=1.0, spin_y=0.0, events=()):
    return engine.ShotResult(outcome, 1.0, (x, y, -0.12), (0, 0, -20), (0, spin_y, 0), list(events) or [outcome])


def test_scoring_goal_bonuses_and_consolation():
    cfg = _config()
    assert score_3d_shot(cfg, _result("goal", x=0.5, y=1.0)) == (20, [])
    assert score_3d_shot(cfg, _result("goal", x=3.0, y=1.0)) == (30, ["corner"])
    assert score_3d_shot(cfg, _result("goal", x=0.2, y=2.1)) == (30, ["corner"])
    assert score_3d_shot(cfg, _result("goal", x=-3.1, y=2.0, spin_y=-30)) == (35, ["corner", "curl"])
    assert score_3d_shot(cfg, _result("save")) == (3, [])
    assert score_3d_shot(cfg, _result("miss", events=["post", "miss"])) == (3, [])
    assert score_3d_shot(cfg, _result("miss")) == (0, [])
    assert score_3d_shot(cfg, _result("wall")) == (0, [])


async def test_one_series_of_six_an_hour(client, db_session, bot_token):
    user = await _register(client, db_session, 850001, bot_token)
    card = await _grant_card(db_session, user.id, rating=88)
    headers = telegram_headers(850001, bot_token)

    start = await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200
    body = start.json()
    assert body["rating"] == 88
    assert body["total_kicks"] == 6
    assert body["kick"]["kick_index"] == 0
    assert 1 <= body["kick"]["seed"] < 2**31

    again = await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})
    assert again.status_code == 409
    assert again.json()["error"]["details"]["hourly_limit"] == 1

    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["free_kick_hourly_limit"] == 1
    assert limits["free_kick"] == 0
    assert "free_kick" in limits["resets_at"]


async def test_a_swipe_answered_instantly_is_refused(client, db_session, bot_token):
    user = await _register(client, db_session, 850002, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850002, bot_token)
    session_id = (await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})).json()["session_id"]

    resp = await client.post(f"/api/v1/games/free-kick-3d/{session_id}/shot", headers=headers, json=SWIPE)
    assert resp.status_code == 409


async def test_rejects_a_downward_swipe(client, db_session, bot_token):
    user = await _register(client, db_session, 850003, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850003, bot_token)
    session_id = (await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})).json()["session_id"]

    resp = await client.post(f"/api/v1/games/free-kick-3d/{session_id}/shot", headers=headers, json={**SWIPE, "dy": 120})
    assert resp.status_code == 422


async def test_full_series_is_replayed_on_the_server_and_paid_once(client, db_session, bot_token):
    user = await _register(client, db_session, 850004, bot_token)
    card = await _grant_card(db_session, user.id, rating=80)
    headers = telegram_headers(850004, bot_token)
    config = await get_config(db_session)
    start = (await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})).json()
    session_id = start["session_id"]

    expected_total = 0
    for i in range(6):
        kick = await _age_current_kick(db_session, session_id)
        resp = await client.post(f"/api/v1/games/free-kick-3d/{session_id}/shot", headers=headers, json=SWIPE)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # The outcome is the server's own replay of this seed + swipe.
        replay = engine.simulate_shot(
            engine.create_setup(kick["seed"], 80), engine.Swipe(SWIPE["dx"], SWIPE["dy"], SWIPE["curve"], SWIPE["duration_ms"]),
        )
        coins, bonuses = score_3d_shot(config, replay)
        assert body["outcome"] == replay.outcome
        assert body["coins_this_kick"] == coins
        assert body["bonuses"] == bonuses
        expected_total += coins
        assert body["total_coins"] == expected_total
        assert body["is_finished"] is (i == 5)
        assert (body["next_kick"] is None) is (i == 5)

    late = await client.post(f"/api/v1/games/free-kick-3d/{session_id}/shot", headers=headers, json=SWIPE)
    assert late.status_code == 409

    before = (await get_user_by_telegram_id(db_session, 850004)).balance
    claim = await client.post(f"/api/v1/games/free-kick/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == expected_total
    assert claim.json()["new_balance"] == before + expected_total
    twice = await client.post(f"/api/v1/games/free-kick/{session_id}/claim", headers=headers)
    assert twice.status_code == 409


async def test_classic_kick_endpoint_refuses_a_3d_session(client, db_session, bot_token):
    user = await _register(client, db_session, 850005, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850005, bot_token)
    session_id = (await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})).json()["session_id"]

    resp = await client.post(f"/api/v1/games/free-kick/{session_id}/kick", headers=headers, json={"elapsed_ms": 0})
    assert resp.status_code == 409


async def test_cannot_play_with_someone_elses_card(client, db_session, bot_token):
    owner = await _register(client, db_session, 850006, bot_token)
    await _register(client, db_session, 850007, bot_token)
    card = await _grant_card(db_session, owner.id)

    resp = await client.post(
        "/api/v1/games/free-kick-3d/start", headers=telegram_headers(850007, bot_token), json={"user_card_id": card.id},
    )
    assert resp.status_code == 403
