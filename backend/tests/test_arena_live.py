"""Card Arena live layer: resume / abandon, the clock and auto-picks, half-time,
all-in, penalties replayed by the server, match goals, the weekend cup, the
defense log with revenge and the picker's server filter."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.arena_cup import ArenaCupRun
from app.models.enums import MatchDifficulty, MatchResult, MatchStatus, TransactionType
from app.models.match import Match
from app.models.transaction import CoinTransaction
from app.services import arena_cup_service, arena_moments, match_service
from app.services import free_kick_3d_engine as kick_engine
from tests.factories import get_user_by_telegram_id
from tests.test_arena_divisions import _config
from tests.test_lineups_matches import _build_full_squad, _play_to_completion
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _ready(client, db_session, bot_token, telegram_id: int):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    return headers, user


async def _play(client, headers) -> dict:
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    return resp.json()


async def _set_state(db_session, match_id: int, **changes) -> None:
    match = await db_session.get(Match, match_id)
    await db_session.refresh(match)
    match.server_state = {**match.server_state, **changes}
    db_session.add(match)
    await db_session.commit()


async def test_a_second_kickoff_goes_back_to_the_running_match(client, db_session, bot_token):
    headers, user = await _ready(client, db_session, bot_token, 760001)
    match = await _play(client, headers)
    assert match["status"] == "in_progress"

    await db_session.refresh(user)
    used = user.match_hourly_attempts
    again = await _play(client, headers)
    assert again["id"] == match["id"] and again["resumed"] is True

    active = (await client.get("/api/v1/matches/active", headers=headers)).json()
    assert active["id"] == match["id"] and active["resumed"] is True
    await db_session.refresh(user)
    assert user.match_hourly_attempts == used


async def test_an_abandoned_match_closes_as_a_loss(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760002)
    match = await _play(client, headers)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    await _set_state(db_session, match["id"], touched_at=stale)

    assert (await client.get("/api/v1/matches/active", headers=headers)).json() is None
    closed = (await client.get(f"/api/v1/matches/{match['id']}", headers=headers)).json()
    assert closed["status"] == "finished" and closed["result"] == "loss"


async def test_auto_answers_every_moment_of_a_match(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760003)
    match = await _play(client, headers)
    kinds = set()
    guard = 0
    while match["status"] == "in_progress":
        guard += 1
        assert guard < 40
        kinds.add(match["pending_moment"]["kind"])
        resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "auto"})
        assert resp.status_code == 200
        match = resp.json()
    assert "halftime" in kinds  # every live match stops at half-time
    assert match["report"]["mvp"] is None or "name" in match["report"]["mvp"]


async def test_an_action_the_moment_lacks_is_refused(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760004)
    match = await _play(client, headers)
    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "all_in"})
    assert resp.status_code == 409


async def test_an_answer_after_the_clock_is_an_auto_pick(client, db_session, bot_token, monkeypatch):
    headers, _user = await _ready(client, db_session, bot_token, 760005)
    match = await _play(client, headers)
    # Any legal action is overridden; the "all_in" above would be refused.
    await _set_state(db_session, match["id"], deadline_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())
    seen = []
    real = arena_moments.auto_action
    monkeypatch.setattr(arena_moments, "auto_action", lambda *a: seen.append(1) or real(*a))
    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "all_in"})
    assert resp.status_code == 200 and seen


def _state(style="possession"):
    balance = {"user_style": style, "opponent_style": "attacking", "user_formation": "4-3-3", "opponent_formation": "4-3-3"}
    return {
        "balance": balance, "kick": {"user_strength": 900, "opponent_strength": 900}, "user_score": 0, "opponent_score": 0,
    }


def test_late_call_only_comes_up_when_behind():
    late = {"kind": "late_call", "team": "user", "minute": 80, "actions": ["all_in", "hold"]}
    state = {
        **_state(), "moments": [late], "next_index": 0, "user_score": 2, "opponent_score": 1,
    }
    match_service._advance(state, _config(), "B")
    assert state["next_index"] == 1  # ahead: nothing to ask

    state.update(next_index=0, user_score=0)
    match_service._advance(state, _config(), "B")
    assert state["next_index"] == 0  # behind: it waits for the answer


def test_auto_never_gambles_on_the_special_moments():
    config = _config()
    assert arena_moments.auto_action({"kind": "halftime"}, {}, config) == "keep_style"
    assert arena_moments.auto_action({"kind": "late_call"}, {}, config) == "hold"
    assert arena_moments.auto_action({"kind": "penalty"}, {}, config) == "auto_penalty"


def test_a_penalty_is_decided_by_replaying_the_swipe():
    config = _config()
    seed, rating = 123456, 80
    moment = {"kind": "penalty", "team": "user", "minute": 30, "seed": seed, "rating": rating, "taker": {"name": "T"}}
    setup = kick_engine.create_penalty_setup(seed, rating)
    swipe = SimpleNamespace(dx=0, dy=0, curve=0, duration_ms=300)
    expected = kick_engine.simulate_shot(setup, kick_engine.Swipe(0, 0, 0, 300)).outcome
    payload = SimpleNamespace(swipe=swipe, dive=None, style=None)
    event, scored = match_service._resolve_penalty(moment, "kick", {}, config, "B", payload)
    assert (scored == "user") == (expected == "goal")
    assert event["payload"]["is_penalty"] is True


@pytest.mark.parametrize("code,user,opp,yes", [
    ("clean_sheet", 2, 0, True), ("clean_sheet", 2, 1, False), ("clean_sheet", 0, 0, False),
    ("win_by_two", 3, 1, True), ("win_by_two", 2, 1, False),
    ("score_three", 3, 4, True), ("score_three", 2, 0, False),
])
def test_match_goals(code, user, opp, yes):
    assert arena_moments.goal_done(code, user, opp, {}) is yes


async def test_preview_hides_the_real_style_and_keeps_the_goal(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760006)
    preview = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert "opponent_style" not in preview and "matchup" not in preview
    assert preview["goal_text"] in arena_moments.MATCH_GOALS.values()
    again = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert again["goal_text"] == preview["goal_text"]
    assert again["opponent_style_hint"] == preview["opponent_style_hint"]


async def test_a_match_goal_pays_on_top(client, db_session, bot_token, monkeypatch):
    headers, user = await _ready(client, db_session, bot_token, 760007)
    monkeypatch.setattr(arena_moments, "goal_done", lambda *a: True)
    match = await _play_to_completion(client, headers)
    bonus = (await db_session.execute(
        select(CoinTransaction).where(
            CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.arena_goal_bonus,
        )
    )).scalars().all()
    assert len(bonus) == 1 and bonus[0].related_object_id == match["id"]


async def test_cup_round_leaves_the_ladder_and_settles_the_run(client, db_session, bot_token, monkeypatch):
    headers, user = await _ready(client, db_session, bot_token, 760008)
    monkeypatch.setattr(arena_cup_service, "is_open", lambda *a: True)
    await db_session.refresh(user)
    points = user.arena_points

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"mode": "cup"})
    assert resp.status_code == 200
    match = resp.json()
    while match["status"] == "in_progress":
        match = (await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "auto"})).json()

    assert match["rating_delta"] == 0 and match["ladder"] is None
    await db_session.refresh(user)
    assert user.arena_points == points
    run = await db_session.scalar(select(ArenaCupRun).where(ArenaCupRun.user_id == user.id))
    await db_session.refresh(run)
    assert (run.status == "active" and run.rounds_won == 1) or (run.status == "lost" and run.rounds_won == 0)


async def test_cup_is_closed_on_weekdays(client, db_session, bot_token, monkeypatch):
    headers, _user = await _ready(client, db_session, bot_token, 760009)
    monkeypatch.setattr(arena_cup_service, "is_open", lambda *a: False)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"mode": "cup"})
    assert resp.status_code == 409


async def test_defense_log_and_one_revenge(client, db_session, bot_token):
    attacker_headers, attacker = await _ready(client, db_session, bot_token, 760010)
    headers, user = await _ready(client, db_session, bot_token, 760011)
    match = Match(
        user_id=attacker.id, opponent_user_id=user.id, opponent_name="Я", difficulty=MatchDifficulty.medium,
        user_team_strength=900, opponent_team_strength=900, user_score=3, opponent_score=1,
        status=MatchStatus.finished, result=MatchResult.win, server_state={},
    )
    db_session.add(match)
    await db_session.commit()

    stats = (await client.get("/api/v1/matches/stats", headers=headers)).json()
    assert stats["defense_unread"] == 1 and stats["hourly_left"] > 0

    log = (await client.get("/api/v1/matches/defense-log", headers=headers)).json()
    assert log[0]["result"] == "loss" and log[0]["my_score"] == 1 and log[0]["can_revenge"] is True

    resp = await client.post("/api/v1/matches/defense-log/seen", headers=headers)
    assert resp.status_code == 204
    assert (await client.get("/api/v1/matches/stats", headers=headers)).json()["defense_unread"] == 0

    preview = await client.post(f"/api/v1/matches/{match.id}/revenge", headers=headers)
    assert preview.status_code == 200 and preview.json()["revenge"] is True
    assert (await client.post(f"/api/v1/matches/{match.id}/revenge", headers=headers)).status_code == 409
    # Only the one who was attacked can answer it.
    assert (await client.post(f"/api/v1/matches/{match.id}/revenge", headers=attacker_headers)).status_code == 404


async def test_a_win_notifies_the_defender_once_a_day(client, db_session, bot_token):
    attacker_headers, attacker = await _ready(client, db_session, bot_token, 760012)
    _headers, user = await _ready(client, db_session, bot_token, 760013)
    await match_service._notify_defender(db_session, SimpleNamespace(opponent_user_id=user.id, id=1))
    await db_session.commit()
    await db_session.refresh(user)
    first = user.arena_defense_notified_at
    assert first is not None
    await match_service._notify_defender(db_session, SimpleNamespace(opponent_user_id=user.id, id=2))
    await db_session.commit()
    await db_session.refresh(user)
    assert user.arena_defense_notified_at == first


async def test_picker_filter_is_by_line_on_the_server(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760014)
    resp = await client.get("/api/v1/collection/cards", headers=headers, params={"position_category": "GK", "limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"]
    assert all(item["player"]["position"] == "GK" for item in body["items"])


def test_their_penalty_is_decided_by_replaying_the_dive():
    seed = 987654
    moment = {"kind": "penalty", "team": "opponent", "minute": 60, "seed": seed, "rating": 80, "taker": {"name": "T"}}
    _, bot_swipe = kick_engine.penalty_bot_shot(seed)
    dive = SimpleNamespace(x=-1500, y=900, reaction_ms=120)
    expected = kick_engine.simulate_shot(
        kick_engine.player_keeper_setup(seed, kick_engine.Dive(dive.x, dive.y, dive.reaction_ms)), bot_swipe,
    ).outcome
    payload = SimpleNamespace(swipe=None, dive=dive, style=None)
    _event, scored = match_service._resolve_penalty(moment, "dive", {}, _config(), "B", payload)
    assert (scored == "opponent") == (expected == "goal")


def test_an_open_goal_still_has_a_scorer():
    squad = [{"user_card_id": 7, "name": "Форвард", "rating": 80, "position": "ST", "category": "FWD", "image_path": None, "rarity": "gold"}]
    state = {"squads": {"user": squad, "opponent": None}, "user_score": 1, "opponent_score": 0}
    event = {"minute": 10, "description": "Гол", "payload": {"shot_type": "empty_net"}}
    arena_moments.finish_goal(event, "user", state, {"actors": {}})
    assert event["payload"]["shooter_id"] == 7 and "Форвард" in event["description"]


async def test_preview_names_the_key_duel(client, db_session, bot_token):
    headers, _user = await _ready(client, db_session, bot_token, 760060)
    preview = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    duel = preview["key_duel"]
    # Your star is a real card, never the keeper; a bot answers with a catalog
    # face of the facing line, at that line's rating.
    assert duel["me"]["position"] != "GK" and duel["me"]["name"]
    assert duel["vs"]["rarity"] and not duel["vs"]["name"].startswith("Их ")
    assert duel["vs"]["rating"] in {line["opponent"] for line in preview["lines"]}
    assert duel["vs"]["rating"] > 0 and duel["vs"]["name"]
    again = (await client.post("/api/v1/matches/opponent", headers=headers)).json()
    assert again["key_duel"] == duel
