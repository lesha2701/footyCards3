from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.models.game import GameSession
from app.services import free_kick_3d_engine as engine
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _grant_card, _register
from tests.utils import telegram_headers

SWIPE = {"dx": 50, "dy": -110, "curve": 0, "duration_ms": 160}
DIVE = {"x": 2200, "y": 800, "reaction_ms": 150}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


async def _age_current_kick(db_session, session_id: int) -> dict:
    session = await db_session.get(GameSession, session_id)
    await db_session.refresh(session)
    state = dict(session.server_state)
    kicks = [dict(k) for k in state["kicks"]]
    i = state["kicks_taken"]
    kicks[i]["issued_at"] = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
    state["kicks"] = kicks
    session.server_state = state
    flag_modified(session, "server_state")
    db_session.add(session)
    await db_session.commit()
    return kicks[i]


async def _start(client, db_session, bot_token, telegram_id, rating=80):
    user = await _register(client, db_session, telegram_id, bot_token)
    card = await _grant_card(db_session, user.id, rating=rating)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post("/api/v1/games/penalty-3d/start", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 200, resp.text
    return headers, resp.json()


async def test_a_shootout_is_replayed_kick_by_kick_and_paid(client, db_session, bot_token):
    headers, start = await _start(client, db_session, bot_token, 860001, rating=80)
    assert start["rating"] == 80
    assert start["kick"] == {"kick_index": 0, "kicker": "player", "seed": start["kick"]["seed"]}
    sid = start["session_id"]
    config = await get_config(db_session)

    scores = {"player": 0, "bot": 0}
    body = None
    for i in range(40):
        kick = await _age_current_kick(db_session, sid)
        if kick["kicker"] == "player":
            resp = await client.post(f"/api/v1/games/penalty-3d/{sid}/shot", headers=headers, json=SWIPE)
            shot = engine.simulate_shot(
                engine.create_penalty_setup(kick["seed"], 80),
                engine.Swipe(SWIPE["dx"], SWIPE["dy"], SWIPE["curve"], SWIPE["duration_ms"]),
            )
        else:
            dive = DIVE if i % 4 == 1 else None
            resp = await client.post(f"/api/v1/games/penalty-3d/{sid}/save", headers=headers, json={"dive": dive})
            d = engine.Dive(dive["x"], dive["y"], dive["reaction_ms"]) if dive else None
            kind, bot_swipe = engine.penalty_bot_shot(kick["seed"], d)
            shot = engine.simulate_shot(engine.player_keeper_setup(kick["seed"], d), bot_swipe)
            assert resp.json()["bot_kind"] == kind
        assert resp.status_code == 200, resp.text
        body = resp.json()
        expected = "save" if shot.outcome == "save" else "goal" if shot.outcome == "goal" else "miss"
        assert body["kicker"] == kick["kicker"] and body["outcome"] == expected
        if expected == "goal":
            scores[kick["kicker"]] += 1
        assert (body["player_score"], body["bot_score"]) == (scores["player"], scores["bot"])
        if body["is_finished"]:
            break
        assert body["next_kick"]["kicker"] == ("player" if (i + 1) % 2 == 0 else "bot")
    assert body["is_finished"] and i + 1 >= 10 and (i + 1) % 2 == 0
    assert body["result"] == ("win" if scores["player"] > scores["bot"] else "loss")
    assert body["rating_delta"] == (3 if body["result"] == "win" else -1)

    late = await client.post(f"/api/v1/games/penalty-3d/{sid}/shot", headers=headers, json=SWIPE)
    assert late.status_code == 409
    claim = await client.post(f"/api/v1/games/penalty/{sid}/claim", headers=headers)
    assert claim.status_code == 200
    reward = config.penalty_reward_win if body["result"] == "win" else config.penalty_reward_loss
    assert claim.json()["reward_coins"] == reward and claim.json()["result"] == body["result"]


async def test_the_kicks_alternate_and_need_a_human_moment(client, db_session, bot_token):
    headers, start = await _start(client, db_session, bot_token, 860002)
    sid = start["session_id"]
    # Instantly: refused.
    assert (await client.post(f"/api/v1/games/penalty-3d/{sid}/shot", headers=headers, json=SWIPE)).status_code == 409
    await _age_current_kick(db_session, sid)
    # The player shoots first: no saving yet.
    assert (await client.post(f"/api/v1/games/penalty-3d/{sid}/save", headers=headers, json={"dive": None})).status_code == 409
    first = await client.post(f"/api/v1/games/penalty-3d/{sid}/shot", headers=headers, json=SWIPE)
    assert first.status_code == 200 and first.json()["next_kick"]["kicker"] == "bot"
    await _age_current_kick(db_session, sid)
    assert (await client.post(f"/api/v1/games/penalty-3d/{sid}/shot", headers=headers, json=SWIPE)).status_code == 409
    bad = await client.post(f"/api/v1/games/penalty-3d/{sid}/save", headers=headers, json={"dive": {**DIVE, "x": 9000}})
    assert bad.status_code == 422


async def test_classic_endpoints_and_forfeit(client, db_session, bot_token):
    headers, start = await _start(client, db_session, bot_token, 860003)
    sid = start["session_id"]
    classic = await client.post(f"/api/v1/games/penalty/{sid}/kick", headers=headers, json={"direction": "top_left"})
    assert classic.status_code == 409
    forfeit = await client.post(f"/api/v1/games/penalty/{sid}/forfeit", headers=headers)
    assert forfeit.status_code == 200 and forfeit.json()["result"] == "loss"
    user = await get_user_by_telegram_id(db_session, 860003)
    await db_session.refresh(user)
    assert user.penalty_rating == 0  # -1, clamped at 0 for a fresh player


async def test_cannot_shoot_with_someone_elses_card(client, db_session, bot_token):
    owner = await _register(client, db_session, 860004, bot_token)
    await _register(client, db_session, 860005, bot_token)
    card = await _grant_card(db_session, owner.id)
    resp = await client.post(
        "/api/v1/games/penalty-3d/start", headers=telegram_headers(860005, bot_token), json={"user_card_id": card.id},
    )
    assert resp.status_code == 403
