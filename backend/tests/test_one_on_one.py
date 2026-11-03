from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.models.game import GameSession
from app.schemas.game import OneOnOneAttackRequest
from app.services import one_on_one_engine as engine
from app.services.game_config_service import get_config
from app.services.one_on_one_service import score_attack, to_timeline
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _grant_card, _register
from tests.utils import telegram_headers

# Run straight at him, feint at tick 120, shoot to the open side.
ATTACK = {
    "controls": [[0, 1, 0], [90, 1, 200]],
    "feint": {"tick": 120, "dir": 1},
    "shot": {"tick": 140, "dx": 60, "dy": -140, "curve": 0, "duration_ms": 140},
}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


async def _age_current_attack(db_session, session_id: int, seconds: float = 15) -> dict:
    """Pretend the attack took its real time to play."""
    session = await db_session.get(GameSession, session_id)
    await db_session.refresh(session)
    state = dict(session.server_state)
    attacks = [dict(a) for a in state["attacks"]]
    idx = state["current_index"]
    attacks[idx]["issued_at"] = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()
    state["attacks"] = attacks
    session.server_state = state
    flag_modified(session, "server_state")
    db_session.add(session)
    await db_session.commit()
    return attacks[idx]


def _end(outcome, feint=None, chip=False, events=()):
    flight = None
    if events:
        flight = engine.Flight("miss", 0, 10, 0, 5, 0, False, None, 1, (0, 0, 0), (0, 0, 0), list(events))
    return engine.EpisodeEnd(outcome, 100, feint, chip, flight)


def test_scoring_goal_bonuses_and_consolation():
    cfg = SimpleNamespace(
        one_on_one_goal_coins=20, one_on_one_feint_bonus=10, one_on_one_chip_bonus=15, one_on_one_near_coins=3,
    )
    assert score_attack(cfg, _end("goal")) == (20, [])
    assert score_attack(cfg, _end("goal", feint="bit")) == (30, ["feint"])
    assert score_attack(cfg, _end("goal", feint="read")) == (20, [])
    assert score_attack(cfg, _end("goal", feint="bit", chip=True)) == (45, ["feint", "chip"])
    assert score_attack(cfg, _end("save")) == (3, [])
    assert score_attack(cfg, _end("miss", events=["post", "miss"])) == (3, [])
    assert score_attack(cfg, _end("miss")) == (0, [])
    assert score_attack(cfg, _end("tackle")) == (0, [])
    assert score_attack(cfg, _end("lost")) == (0, [])


def test_timeline_validation():
    ok = OneOnOneAttackRequest(**ATTACK)
    assert OneOnOneAttackRequest(**{**ATTACK, "controls": [[0, 2, 0]]}).controls == [[0, 2, 0]]
    assert to_timeline(ok).shot[0] == 140
    for bad in (
        {**ATTACK, "controls": [[0, 1, 0], [0, 0, 0]]},  # ticks must ascend
        {**ATTACK, "controls": [[0, 3, 0]]},  # hold is 0/1/2 (stop, run, sprint)
        {**ATTACK, "controls": [[0, 1, 1001]]},  # steer within ±1000
        {**ATTACK, "controls": [[0, 1]]},
        {**ATTACK, "feint": {"tick": 10, "dir": 0}},
        {**ATTACK, "shot": {**ATTACK["shot"], "dy": 50}},  # a shot goes upwards
        {**ATTACK, "shot": {**ATTACK["shot"], "tick": 601}},
    ):
        with pytest.raises(ValueError):
            OneOnOneAttackRequest(**bad)


async def test_series_is_replayed_on_the_server_and_paid_once(client, db_session, bot_token):
    user = await _register(client, db_session, 870001, bot_token)
    card = await _grant_card(db_session, user.id, rating=82)
    headers = telegram_headers(870001, bot_token)
    config = await get_config(db_session)

    start = await client.post("/api/v1/games/one-on-one/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200, start.text
    body = start.json()
    assert body["rating"] == 82
    assert body["total_attacks"] == config.one_on_one_attacks
    session_id = body["session_id"]

    expected_total = 0
    outcomes = set()
    for i in range(config.one_on_one_attacks):
        attack = await _age_current_attack(db_session, session_id)
        resp = await client.post(f"/api/v1/games/one-on-one/{session_id}/attack", headers=headers, json=ATTACK)
        assert resp.status_code == 200, resp.text
        out = resp.json()
        # The verdict is the server's own replay of this seed + timeline.
        replay = engine.replay_episode(
            engine.create_episode(attack["seed"], 82), to_timeline(OneOnOneAttackRequest(**ATTACK)),
        )
        coins, bonuses = score_attack(config, replay)
        assert (out["outcome"], out["coins_this_attack"], out["bonuses"], out["feint"]) == (
            replay.outcome, coins, bonuses, replay.feint,
        )
        outcomes.add(replay.outcome)
        expected_total += coins
        assert out["total_coins"] == expected_total
        assert out["is_finished"] is (i == config.one_on_one_attacks - 1)

    late = await client.post(f"/api/v1/games/one-on-one/{session_id}/attack", headers=headers, json=ATTACK)
    assert late.status_code == 409

    before = (await get_user_by_telegram_id(db_session, 870001)).balance
    claim = await client.post(f"/api/v1/games/one-on-one/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json() == {"reward_coins": expected_total, "new_balance": before + expected_total}
    twice = await client.post(f"/api/v1/games/one-on-one/{session_id}/claim", headers=headers)
    assert twice.status_code == 409


async def test_an_attack_answered_faster_than_it_plays_is_refused(client, db_session, bot_token):
    user = await _register(client, db_session, 870002, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(870002, bot_token)
    session_id = (await client.post("/api/v1/games/one-on-one/start", headers=headers, json={"user_card_id": card.id})).json()["session_id"]

    # 140 ticks are 2.3 s of play: answered at once, it can't be genuine.
    resp = await client.post(f"/api/v1/games/one-on-one/{session_id}/attack", headers=headers, json=ATTACK)
    assert resp.status_code == 409
    # Taking the time it takes is fine.
    await _age_current_attack(db_session, session_id, seconds=3)
    ok = await client.post(f"/api/v1/games/one-on-one/{session_id}/attack", headers=headers, json=ATTACK)
    assert ok.status_code == 200, ok.text


async def test_hourly_cap_is_the_shared_one(client, db_session, bot_token):
    user = await _register(client, db_session, 870003, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(870003, bot_token)
    config = await get_config(db_session)
    for _ in range(config.hourly_game_limit):
        ok = await client.post("/api/v1/games/one-on-one/start", headers=headers, json={"user_card_id": card.id})
        assert ok.status_code == 200
    over = await client.post("/api/v1/games/one-on-one/start", headers=headers, json={"user_card_id": card.id})
    assert over.status_code == 409
    assert over.json()["error"]["details"]["hourly_limit"] == config.hourly_game_limit
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["one_on_one"] == 0
    assert "one_on_one" in limits["resets_at"]


async def test_past_the_daily_cap_the_series_pays_nothing(client, db_session, bot_token):
    user = await _register(client, db_session, 870004, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(870004, bot_token)
    config = await get_config(db_session)
    config.one_on_one_attacks = 1
    config.one_on_one_daily_limit = 0
    config.one_on_one_near_coins = 5
    config.one_on_one_goal_coins = 5
    db_session.add(config)
    await db_session.commit()

    session_id = (await client.post("/api/v1/games/one-on-one/start", headers=headers, json={"user_card_id": card.id})).json()["session_id"]
    await _age_current_attack(db_session, session_id)
    played = await client.post(f"/api/v1/games/one-on-one/{session_id}/attack", headers=headers, json=ATTACK)
    assert played.json()["is_finished"] is True
    claim = await client.post(f"/api/v1/games/one-on-one/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0


async def test_cannot_play_with_someone_elses_card(client, db_session, bot_token):
    owner = await _register(client, db_session, 870005, bot_token)
    await _register(client, db_session, 870006, bot_token)
    card = await _grant_card(db_session, owner.id)
    resp = await client.post(
        "/api/v1/games/one-on-one/start", headers=telegram_headers(870006, bot_token), json={"user_card_id": card.id},
    )
    assert resp.status_code == 403


async def test_someone_elses_session_is_forbidden(client, db_session, bot_token):
    owner = await _register(client, db_session, 870007, bot_token)
    await _register(client, db_session, 870008, bot_token)
    card = await _grant_card(db_session, owner.id)
    session_id = (await client.post(
        "/api/v1/games/one-on-one/start", headers=telegram_headers(870007, bot_token), json={"user_card_id": card.id},
    )).json()["session_id"]
    await _age_current_attack(db_session, session_id)
    resp = await client.post(
        f"/api/v1/games/one-on-one/{session_id}/attack", headers=telegram_headers(870008, bot_token), json=ATTACK,
    )
    assert resp.status_code == 403
