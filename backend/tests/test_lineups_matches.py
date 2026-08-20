import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource
from app.models.game_config import GameConfig
from app.services import match_service
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS, get_active_lineup
from app.services.match_situations import ATTACK_SITUATIONS, DEFENSE_SITUATIONS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # The in-memory rate limiter (app/core/rate_limit.py) is keyed by numeric
    # user id and lives for the whole pytest process, but every test gets a
    # fresh DB (autoincrement ids restart at 1) — without this, unrelated
    # tests would contend for the same "play_match:1" bucket and could trip
    # each other's rate limit.
    rate_limit_module._hits.clear()
    yield


async def _build_full_squad(db_session, user_id: int) -> list[dict]:
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    return slots


async def _force_shot_type(db_session, *, in_box=0, long_range=0, empty_net=0):
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.match_shot_type_in_box_weight = in_box
    config.match_shot_type_long_range_weight = long_range
    config.match_shot_type_empty_net_weight = empty_net
    await db_session.commit()


async def _get_config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
        config = await db_session.get(GameConfig, 1)
    return config


# One deterministic action per pending-moment kind, so a full match can be
# played out end-to-end without needing to control which kind of moment the
# random queue generates at any given step.
_ACTION_BY_KIND = {"attack": "shoot", "defense": "tackle", "breakaway": "strike"}


async def _play_to_completion(client, headers) -> dict:
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    match = resp.json()
    guard = 0
    while match["status"] == "in_progress":
        guard += 1
        assert guard < 30  # sanity bound — the moment queue is at most 22 long
        pending = match["pending_moment"]
        assert pending is not None
        action = _ACTION_BY_KIND[pending["kind"]]
        resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": action})
        assert resp.status_code == 200
        match = resp.json()
    return match


async def test_set_lineup_success(client, db_session, bot_token):
    headers = telegram_headers(750001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750001)

    slots = await _build_full_squad(db_session, user.id)
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert body["team_strength"] > 0


async def test_cannot_use_other_users_card_in_lineup(client, db_session, bot_token):
    headers = telegram_headers(750002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    owner, _ = None, None

    other_headers = telegram_headers(750003, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other_user = await get_user_by_telegram_id(db_session, 750003)

    player = await create_player(db_session, position=FORMATION_SLOTS[0].ideal_position)
    other_card = await create_user_card(db_session, other_user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.put(
        "/api/v1/lineups/active", headers=headers,
        json={"slots": [{"slot_code": FORMATION_SLOTS[0].code, "user_card_id": other_card.id}]},
    )
    assert resp.status_code == 403


async def test_cannot_use_duplicate_player_copies_in_two_slots(client, db_session, bot_token):
    headers = telegram_headers(750008, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750008)

    slot_a, slot_b = FORMATION_SLOTS[1], FORMATION_SLOTS[2]  # both DEF slots
    player = await create_player(db_session, position=slot_a.ideal_position)
    card1 = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    card2 = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.put(
        "/api/v1/lineups/active", headers=headers,
        json={"slots": [
            {"slot_code": slot_a.code, "user_card_id": card1.id},
            {"slot_code": slot_b.code, "user_card_id": card2.id},
        ]},
    )
    assert resp.status_code == 409


async def test_set_lineup_tactic(client, db_session, bot_token):
    headers = telegram_headers(750007, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750007)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.get("/api/v1/lineups/active", headers=headers)
    assert resp.json()["tactic"] == "balanced"

    resp = await client.post("/api/v1/lineups/tactic", headers=headers, json={"tactic": "attacking"})
    assert resp.status_code == 200
    assert resp.json()["tactic"] == "attacking"

    resp = await client.post("/api/v1/lineups/tactic", headers=headers, json={"tactic": "not-a-tactic"})
    assert resp.status_code == 409


async def test_play_match_requires_complete_lineup(client, bot_token):
    headers = telegram_headers(750004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409


async def test_play_match_starts_in_progress(client, db_session, bot_token):
    headers = telegram_headers(750005, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750005)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("in_progress", "finished")
    if body["status"] == "in_progress":
        assert body["result"] is None
        assert body["pending_moment"] is not None
        assert body["pending_moment"]["shot_type"] in ("in_box", "long_range", "empty_net")
        assert body["pending_moment"]["team"] in ("user", "opponent")
        assert body["pending_moment"]["kind"] in ("attack", "defense", "breakaway")
        assert body["pending_moment"]["description"]
        assert body["pending_moment"]["actions"]

    await db_session.refresh(user)
    assert user.match_hourly_attempts == 1


async def test_act_rejects_wrong_owner(client, db_session, bot_token):
    headers_a = telegram_headers(750101, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    user_a = await get_user_by_telegram_id(db_session, 750101)
    slots = await _build_full_squad(db_session, user_a.id)
    await client.put("/api/v1/lineups/active", headers=headers_a, json={"slots": slots})

    headers_b = telegram_headers(750102, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_b)

    await _force_shot_type(db_session, in_box=100)
    resp = await client.post("/api/v1/matches/play", headers=headers_a, json={"difficulty": "medium"})
    match = resp.json()
    assert match["status"] == "in_progress"

    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers_b, json={"action": "shoot"})
    assert resp.status_code == 403


async def test_act_rejects_missing_action_field(client, db_session, bot_token):
    headers = telegram_headers(750103, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750103)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _force_shot_type(db_session, in_box=100)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    assert match["status"] == "in_progress"
    assert match["pending_moment"]["shot_type"] == "in_box"

    # `action` is a required field on MatchActionRequest (no more optional
    # `direction` with a None default) — a missing body fails schema
    # validation before the service layer ever runs.
    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={})
    assert resp.status_code == 422


async def test_act_rejects_action_not_available_for_moment(client, db_session, bot_token):
    headers = telegram_headers(750104, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750104)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _force_shot_type(db_session, empty_net=100)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    if match["status"] == "in_progress":
        # With every shot chance forced to empty_net, the only interactive
        # moment the user can reach is their own breakaway — actions=["strike"].
        assert match["pending_moment"]["kind"] == "breakaway"
        assert match["pending_moment"]["actions"] == ["strike"]
        resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "shoot"})
        assert resp.status_code == 409


async def test_act_breakaway_only_accepts_strike(client, db_session, bot_token):
    headers = telegram_headers(750105, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750105)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _force_shot_type(db_session, empty_net=100)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    # A breakaway for the user's own team is still interactive (a single
    # confirm); the opponent's breakaways auto-resolve and never appear as
    # a pending moment.
    if match["status"] == "in_progress":
        assert match["pending_moment"]["shot_type"] == "empty_net"
        assert match["pending_moment"]["kind"] == "breakaway"
        resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "strike"})
        assert resp.status_code == 200


async def test_act_forces_directional_shot_types(client, db_session, bot_token):
    headers = telegram_headers(750106, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750106)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _force_shot_type(db_session, long_range=100)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    if match["status"] == "in_progress":
        assert match["pending_moment"]["shot_type"] == "long_range"
        assert match["pending_moment"]["kind"] in ("attack", "defense")


async def test_match_event_log_stays_ordered_and_matches_score(client, db_session, bot_token):
    headers = telegram_headers(750109, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750109)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    # Force many directional shots so the match needs several separate
    # request/response round trips (start + N shoot calls) to finish —
    # exactly the path where unordered `events` fetches previously let a
    # later-arriving row sort ahead of an earlier one in the log.
    await _force_shot_type(db_session, in_box=50, long_range=50)
    match = await _play_to_completion(client, headers)

    events = match["events"]
    minutes = [e["minute"] for e in events]
    assert minutes == sorted(minutes)

    goals_for_user = sum(1 for e in events if e["event_type"] == "goal" and e["team"] == "user")
    goals_for_opponent = sum(1 for e in events if e["event_type"] == "goal" and e["team"] == "opponent")
    assert goals_for_user == match["user_score"]
    assert goals_for_opponent == match["opponent_score"]


async def test_act_rejects_when_already_finished(client, db_session, bot_token):
    headers = telegram_headers(750107, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750107)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    match = await _play_to_completion(client, headers)
    balance_before = (await client.get("/api/v1/profile/me", headers=headers)).json()["balance"]

    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": "shoot"})
    assert resp.status_code == 409

    balance_after = (await client.get("/api/v1/profile/me", headers=headers)).json()["balance"]
    assert balance_after == balance_before


async def test_full_match_loop_finishes_and_credits_once(client, db_session, bot_token):
    headers = telegram_headers(750109, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750109)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    match = await _play_to_completion(client, headers)
    assert match["result"] in ("win", "draw", "loss")
    assert match["rating_delta"] == {"win": 3, "draw": 1, "loss": -1}[match["result"]]
    assert match["reward_coins"] >= 0

    await db_session.refresh(user)
    assert user.arena_rating == max(0, 0 + match["rating_delta"])


async def test_bot_match_opponent_name_borrows_real_user_even_with_incomplete_lineup(client, db_session, bot_token):
    """opponent_name should borrow a real, non-banned player's display name
    whenever one exists — purely cosmetic — not just when that player's
    lineup happens to also be complete enough to borrow for strength."""
    # Another real user with no lineup at all — ineligible for the
    # strength-borrowing path, but still eligible for the name.
    other_headers = telegram_headers(750150, bot_token)
    await client.post("/api/v1/auth/session", headers=other_headers)
    other = await get_user_by_telegram_id(db_session, 750150)

    headers = telegram_headers(750151, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750151)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    assert resp.json()["opponent_name"] == other.full_display_name()


async def test_bot_match_opponent_name_falls_back_when_no_other_users_exist(client, db_session, bot_token):
    headers = telegram_headers(750152, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750152)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    assert resp.json()["opponent_name"] in match_service.BOT_NAMES


async def test_default_arena_rating_is_zero_for_new_user(client, bot_token):
    headers = telegram_headers(750110, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/matches/stats", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["arena_rating"] == 0


async def test_hourly_limit_not_consumed_by_act_calls(client, db_session, bot_token):
    headers = telegram_headers(750111, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750111)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _play_to_completion(client, headers)

    await db_session.refresh(user)
    assert user.match_hourly_attempts == 1


async def test_arena_leaderboard_reports_table_stats(client, db_session, bot_token):
    headers = telegram_headers(750006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750006)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    match = await _play_to_completion(client, headers)

    board_resp = await client.get("/api/v1/leaderboard/arena", headers=headers)
    assert board_resp.status_code == 200
    entry = next(e for e in board_resp.json() if e["user_id"] == user.id)

    expected_played = {"win": (1, 0, 0), "draw": (0, 1, 0), "loss": (0, 0, 1)}[match["result"]]
    assert (entry["matches_won"], entry["matches_drawn"], entry["matches_lost"]) == expected_played
    assert entry["goal_difference"] == match["user_score"] - match["opponent_score"]
    assert entry["points"] == entry["matches_won"] * 3 + entry["matches_drawn"]


async def test_match_history_excludes_in_progress_matches(client, db_session, bot_token):
    headers = telegram_headers(750112, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750112)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    abandoned_match = resp.json()  # left in_progress on purpose

    finished_match = await _play_to_completion(client, headers)

    resp = await client.get("/api/v1/matches/history", headers=headers)
    assert resp.status_code == 200
    history_ids = [m["id"] for m in resp.json()]
    assert finished_match["id"] in history_ids
    if abandoned_match["status"] == "in_progress":
        assert abandoned_match["id"] not in history_ids


async def test_arena_stats_includes_rank(client, db_session, bot_token):
    headers = telegram_headers(750113, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750113)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _play_to_completion(client, headers)

    resp = await client.get("/api/v1/matches/stats", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["arena_rank"] >= 1


async def test_match_hourly_limit_blocks_after_three_plays(client, db_session, bot_token):
    headers = telegram_headers(750006, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750006)

    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    for _ in range(3):
        resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
        assert resp.status_code == 200

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 3
    assert details["retry_after_seconds"] > 0

    await db_session.refresh(user)
    from datetime import timedelta

    user.match_hour_started_at = user.match_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200


async def test_pending_moment_shape_for_attack(client, db_session, bot_token):
    headers = telegram_headers(750114, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750114)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    lineup = await get_active_lineup(db_session, user)
    moment = match_service._build_shot_moment(10, "user", "in_box", lineup, "Соперник")

    assert moment["situation_kind"] == "attack"
    assert moment["actions"] == ["shoot", "pass"]
    assert moment["description"]
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    assert shooter["name"] and shooter["rating"] and shooter["position"]
    assert pass_target["name"]
    assert pass_target["user_card_id"] != shooter["user_card_id"]
    assert shooter["name"] in moment["description"]
    assert pass_target["name"] in moment["description"]


async def test_pending_moment_shape_for_defense(client, db_session, bot_token):
    headers = telegram_headers(750115, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750115)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    lineup = await get_active_lineup(db_session, user)
    moment = match_service._build_shot_moment(10, "opponent", "in_box", lineup, "Соперник")

    assert moment["situation_kind"] == "defense"
    assert moment["actions"] == ["tackle", "block", "keeper"]
    defender = moment["actors"]["defender"]
    assert defender["name"] and defender["rating"]
    assert defender["name"] in moment["description"]
    assert "Соперник" in moment["description"]


async def test_pass_success_awards_goal_and_credits_assist(db_session, monkeypatch):
    config = await _get_config(db_session)
    situation = next(s for s in ATTACK_SITUATIONS if s.shot_type == "in_box")
    shooter = {"user_card_id": 1, "player_id": 1, "name": "Иван Иванов", "rating": 90, "position": "LW"}
    pass_target = {"user_card_id": 2, "player_id": 2, "name": "Пётр Петров", "rating": 95, "position": "ST"}
    moment = {
        "minute": 10, "situation_id": situation.id, "shot_type": situation.shot_type,
        "actors": {"shooter": shooter, "pass_target": pass_target},
    }
    state = {"ratings": {"opponent_def": 70, "opponent_gk": 70}, "cards": {}, "red_card_applied": False}

    # A random() above every configured chance threshold forces every roll
    # in the chain (pass-fail, miss, save) to take the "success" branch.
    monkeypatch.setattr(match_service.random, "random", lambda: 0.99)
    event, scored_by = match_service._resolve_attack(moment, "pass", state, config, "Соперник")

    assert scored_by == "user"
    assert event["event_type"] == "goal"
    assert event["payload"]["assisted_by"] == shooter["name"]
    assert event["payload"]["shooter"] == pass_target["name"]


def test_apply_card_second_yellow_becomes_red():
    state = {"cards": {}}
    first = match_service._apply_card(state, user_card_id=42, is_red=False)
    assert first == "yellow"
    assert state["cards"]["42"] == {"yellow_count": 1, "sent_off": False}

    second = match_service._apply_card(state, user_card_id=42, is_red=False)
    assert second == "red"
    assert state["cards"]["42"]["sent_off"] is True


async def test_apply_red_card_debuff_reduces_user_def_once(db_session):
    config = await _get_config(db_session)
    config.match_red_card_strength_penalty_pct = 0.20
    await db_session.commit()

    state = {"ratings": {"user_def": 80}, "red_card_applied": False}
    match_service._apply_red_card_debuff(state, config)
    assert state["ratings"]["user_def"] == 64  # 80 * (1 - 0.20)
    assert state["red_card_applied"] is True

    # A second red card in the same match does not stack the debuff.
    match_service._apply_red_card_debuff(state, config)
    assert state["ratings"]["user_def"] == 64


async def test_box_foul_triggers_penalty_continuation(db_session, monkeypatch):
    config = await _get_config(db_session)
    situation = next(s for s in DEFENSE_SITUATIONS if "box" in s.tags)
    defender = {"user_card_id": 5, "player_id": 5, "name": "Олег Дефендеров", "rating": 60, "position": "CB"}
    moment = {
        "minute": 20, "situation_id": situation.id, "shot_type": situation.shot_type,
        "actors": {"defender": defender},
    }
    state = {
        "ratings": {"user_gk": 60, "user_def": 70, "opponent_fwd": 70},
        "cards": {}, "red_card_applied": False,
    }

    # A random() near zero forces every roll (foul, red-card, save) to take
    # the "worst case" branch — always a foul, always a red card.
    monkeypatch.setattr(match_service.random, "random", lambda: 0.01)
    event, scored_by = match_service._resolve_defense(moment, "tackle", state, config, "Соперник")

    assert event["payload"]["is_penalty"] is True
    assert event["payload"]["card"] == "red"
    assert event["event_type"] in ("save", "goal")
    assert scored_by == ("opponent" if event["event_type"] == "goal" else None)
    assert state["cards"]["5"]["sent_off"] is True
    assert state["red_card_applied"] is True


def test_synthesize_bot_ratings_includes_clamped_gk():
    fwd, defence, gk = match_service._synthesize_bot_ratings(
        user_fwd=90, user_def=85, user_gk=80, opponent_strength=200, user_strength=100
    )
    assert 58 <= fwd <= 99
    assert 58 <= defence <= 99
    assert 58 <= gk <= 99
    # opponent_strength is double user_strength, so the ratio (2.0) pushes
    # every synthesized rating up against the clamp ceiling.
    assert fwd == 99 and defence == 99 and gk == 99


async def test_forfeit_counts_as_a_loss(client, db_session, bot_token):
    """Leaving mid-match (confirmed via the frontend's leave dialog) must
    cost the same -1 rating a real loss would — otherwise switching tabs
    and confirming "leave" is a free way to dodge a losing match."""
    headers = telegram_headers(750116, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750116)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _force_shot_type(db_session, in_box=100)
    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    assert match["status"] == "in_progress"

    # Take one action first so the forfeit is a genuine mid-match
    # abandonment, not just forfeiting an untouched match.
    pending = match["pending_moment"]
    action = _ACTION_BY_KIND[pending["kind"]]
    resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": action})
    match = resp.json()

    if match["status"] == "finished":
        return  # the single action happened to finish the match already; nothing left to forfeit

    forfeit = await client.post(f"/api/v1/matches/{match['id']}/forfeit", headers=headers)
    assert forfeit.status_code == 200
    body = forfeit.json()
    assert body["status"] == "finished"
    assert body["result"] == "loss"
    assert body["rating_delta"] == -1

    await db_session.refresh(user)
    assert user.arena_rating == 0  # 0 - 1, clamped at the floor
    assert user.matches_lost == 1


async def test_forfeit_rejects_non_owner(client, db_session, bot_token):
    headers_a = telegram_headers(750117, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    user_a = await get_user_by_telegram_id(db_session, 750117)
    slots = await _build_full_squad(db_session, user_a.id)
    await client.put("/api/v1/lineups/active", headers=headers_a, json={"slots": slots})

    headers_b = telegram_headers(750118, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_b)

    await _force_shot_type(db_session, in_box=100)
    resp = await client.post("/api/v1/matches/play", headers=headers_a, json={"difficulty": "medium"})
    match = resp.json()
    assert match["status"] == "in_progress"

    resp = await client.post(f"/api/v1/matches/{match['id']}/forfeit", headers=headers_b)
    assert resp.status_code == 403


async def test_forfeit_rejects_already_finished_match(client, db_session, bot_token):
    headers = telegram_headers(750119, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 750119)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    match = await _play_to_completion(client, headers)
    assert match["status"] == "finished"

    resp = await client.post(f"/api/v1/matches/{match['id']}/forfeit", headers=headers)
    assert resp.status_code == 409
