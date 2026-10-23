import random
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, NotificationType, Position, TransactionType
from app.models.game_config import GameConfig
from app.models.mordoboi import MordoboiMatch
from app.models.notification import Notification
from app.models.transaction import CoinTransaction
from app.services import mordoboi_engine as engine
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/mordoboi"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest.fixture(autouse=True)
async def _enabled(request, db_session):
    if "disabled" not in request.node.name:
        await _set_config(db_session, mordoboi_enabled=True)
    yield


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _fighter(power=70, speed=70, guard=60, hp=100, stamina=100):
    stats = {"power": power, "speed": speed, "guard": guard, "max_hp": hp, "max_stamina": stamina}
    return engine.new_fighter(stats, None)


def _state(rounds=3, exchanges=4, **kw):
    return engine.new_state(_fighter(**kw), _fighter(**kw), rounds, exchanges)


def _exchange(state, user_action, opp_action, seed=1):
    state["picks"] = {"user": {"action": user_action}, "opponent": {"action": opp_action}}
    return engine.resolve_exchange(state, random.Random(seed))


def test_hook_rides_through_a_jab():
    entry = _exchange(_state(), "hook", "jab")
    assert entry["outcome"] == {"user": "landed", "opponent": "beaten"}
    assert entry["damage"]["user"] > 0 and entry["damage"]["opponent"] == 0


def test_strike_circle_uppercut_beats_hook_and_jab_beats_uppercut():
    assert _exchange(_state(), "uppercut", "hook")["outcome"] == {"user": "landed", "opponent": "beaten"}
    assert _exchange(_state(), "uppercut", "jab")["outcome"] == {"user": "beaten", "opponent": "landed"}


def test_same_strikes_trade():
    entry = _exchange(_state(), "hook", "hook")
    assert entry["damage"]["user"] > 0 and entry["damage"]["opponent"] > 0


def test_block_takes_part_and_the_uppercut_gets_through_most():
    clean = _exchange(_state(), "hook", "hook", seed=3)["damage"]["user"]
    blocked = _exchange(_state(), "hook", "block", seed=3)
    assert blocked["outcome"]["user"] == "blocked" and 0 < blocked["damage"]["user"] < clean
    jab = _exchange(_state(), "jab", "block", seed=3)["damage"]["user"]
    upper = _exchange(_state(), "uppercut", "block", seed=3)["damage"]["user"]
    assert upper > jab


def test_dodge_slips_the_hook_and_counters_but_eats_the_uppercut():
    slip = _exchange(_state(), "hook", "dodge")
    assert slip["outcome"] == {"user": "slipped", "opponent": "counter"}
    assert slip["damage"]["user"] == 0 and slip["damage"]["opponent"] > 0
    caught = _exchange(_state(), "uppercut", "dodge", seed=5)
    clean = _exchange(_state(), "uppercut", "hook", seed=5)
    assert caught["outcome"]["user"] == "caught" and caught["damage"]["user"] > clean["damage"]["user"]


def test_power_and_speed_drive_damage():
    strong = _state()
    strong["fighters"]["user"]["power"] = 95
    weak = _state()
    weak["fighters"]["user"]["power"] = 40
    assert _exchange(strong, "hook", "hook", 7)["damage"]["user"] > _exchange(weak, "hook", "hook", 7)["damage"]["user"]
    fast = _state()
    fast["fighters"]["user"]["speed"] = 95
    slow = _state()
    slow["fighters"]["user"]["speed"] = 40
    assert _exchange(fast, "jab", "jab", 7)["damage"]["user"] > _exchange(slow, "jab", "jab", 7)["damage"]["user"]


def test_stamina_gates_heavy_strikes_but_block_is_always_there():
    s = _state(stamina=60)
    s["fighters"]["user"]["stamina"] = 5
    assert engine.available_actions(s["fighters"]["user"]) == ["jab", "block"]
    with pytest.raises(engine.EngineError):
        engine.validate_pick(s, "user", "uppercut")
    s["fighters"]["user"]["stamina"] = 0
    assert engine.available_actions(s["fighters"]["user"]) == ["block"]
    before = s["fighters"]["user"]["stamina"]
    _exchange(s, "block", "block")
    assert s["fighters"]["user"]["stamina"] == before + engine.STAMINA_REGEN + engine.BLOCK_REGEN


def test_knockout_ends_the_bout():
    s = _state()
    s["fighters"]["opponent"]["hp"] = 3
    entry = _exchange(s, "uppercut", "hook")
    assert s["finished"] and s["winner"] == "user" and s["reason"] == "ko" and entry["end"] == "ko"


def test_points_decision_after_the_last_round_and_corner_recovery():
    s = _state(rounds=2, exchanges=2)
    _exchange(s, "hook", "block")
    s["fighters"]["user"]["stamina"] = 10
    entry = _exchange(s, "jab", "block")  # end of round 1
    assert entry.get("round_end") and s["round"] == 2 and s["exchange"] == 1
    assert s["fighters"]["user"]["stamina"] > 10 + engine.STAMINA_REGEN  # the corner gave some back
    assert s["scorecards"][0] == {"user": 10, "opponent": 9, "damage": s["scorecards"][0]["damage"]}
    _exchange(s, "block", "block")
    _exchange(s, "block", "block")  # round 2 even: 10-10
    assert s["finished"] and s["reason"] == "points" and s["winner"] == "user"
    assert engine.score_totals(s) == {"user": 20, "opponent": 19}


def test_even_bout_is_a_draw():
    s = _state(rounds=1, exchanges=1)
    _exchange(s, "block", "block")
    assert s["finished"] and s["winner"] == "draw"


def test_boxer_stats_follow_the_card():
    winger = engine.boxer_stats(80, 75, 50, "RW", 100)
    centre_back = engine.boxer_stats(80, 75, 85, "CB", 100)
    assert winger["speed"] > centre_back["speed"]
    assert centre_back["power"] > winger["power"] and centre_back["guard"] > winger["guard"]
    assert engine.boxer_stats(90, 80, 80, "CM", 100)["max_stamina"] > engine.boxer_stats(60, 80, 80, "CM", 100)["max_stamina"]


def test_bot_picks_only_affordable_and_ignores_the_secret_pick():
    s = _state()
    s["fighters"]["opponent"]["stamina"] = 5
    for seed in range(50):
        assert engine.bot_choose(s, "opponent", random.Random(seed)) in ("jab", "block")
    s["fighters"]["opponent"]["stamina"] = 100
    a = dict(s, picks={"user": {"action": "hook"}, "opponent": None})
    b = dict(s, picks={"user": {"action": "dodge"}, "opponent": None})
    assert [engine.bot_choose(a, "opponent", random.Random(i)) for i in range(20)] == [
        engine.bot_choose(b, "opponent", random.Random(i)) for i in range(20)
    ]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

async def _set_config(db_session, **overrides) -> None:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()


async def _player(client, db_session, bot_token, telegram_id: int, rating=80, position=Position.ST):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    player = await create_player(db_session, rating=rating, position=position, display_name=f"Boxer {telegram_id}")
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()
    return headers, user, card.id


async def _load_match(db_session, match_id: int) -> MordoboiMatch:
    db_session.expire_all()
    return await db_session.get(MordoboiMatch, match_id)


async def _rewrite_state(db_session, match_id: int, mutate) -> None:
    match = await _load_match(db_session, match_id)
    state = dict(match.server_state)
    mutate(state)
    match.server_state = state
    flag_modified(match, "server_state")
    await db_session.commit()


async def _pick(client, headers, match, action):
    return await client.post(
        f"{API}/matches/{match['id']}/pick", headers=headers, json={"action": action, "version": match["version"]},
    )


def _ko_ready(state):
    # The bot has no stamina left, so it can only block — a jab still
    # gets a point of damage through.
    state["fighters"]["opponent"].update(hp=1, stamina=0)


# ---------------------------------------------------------------------------
# Flag, boxer, bot bouts
# ---------------------------------------------------------------------------

async def test_disabled_flag_blocks_new_bouts(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980001)
    await _set_config(db_session, mordoboi_enabled=False)
    await db_session.commit()
    assert (await client.get(f"{API}/info", headers=headers)).json()["enabled"] is False
    resp = await client.post(f"{API}/matches/bot", headers=headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "disabled"


async def test_boxer_defaults_to_strongest_and_can_be_changed(client, db_session, bot_token):
    headers, user, card_id = await _player(client, db_session, bot_token, 980002, rating=70)
    strong = await create_player(db_session, rating=88, position=Position.RW, display_name="Fast One")
    strong_card = await create_user_card(db_session, user.id, strong.id, CardSource.seed)
    await db_session.commit()
    boxer = (await client.get(f"{API}/boxer", headers=headers)).json()
    assert boxer["selected"]["card"]["user_card_id"] == strong_card.id and len(boxer["options"]) == 2
    changed = (await client.put(f"{API}/boxer", headers=headers, json={"user_card_id": card_id})).json()
    assert changed["selected"]["card"]["user_card_id"] == card_id

    other_headers, _, other_card = await _player(client, db_session, bot_token, 980003)
    assert (await client.put(f"{API}/boxer", headers=other_headers, json={"user_card_id": card_id})).status_code == 403
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert match["me"]["card"]["user_card_id"] == card_id


async def test_no_cards_no_bout(client, db_session, bot_token):
    headers = telegram_headers(980004, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 409


async def test_bot_bout_resolves_each_pick_and_hides_nothing_unfair(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980005)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert match["status"] == "in_progress" and match["can_pick"] and match["round"] == 1 and match["exchange"] == 1
    assert set(match["available_actions"]) == set(engine.ACTIONS)
    after = (await _pick(client, headers, match, "jab")).json()
    assert len(after["log"]) == 1 and after["exchange"] == 2 and after["version"] == match["version"] + 1
    assert after["log"][0]["my_action"] == "jab" and after["log"][0]["opponent_action"] in engine.ACTIONS
    assert after["my_pick"] is None and after["can_pick"]


async def test_bot_bout_to_the_end_pays_reward_and_rating(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1)
    headers, user, _ = await _player(client, db_session, bot_token, 980006)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _rewrite_state(db_session, match["id"], _ko_ready)
    end = (await _pick(client, headers, match, "jab")).json()
    assert end["result"] == "win" and end["log"][-1]["opponent_action"] == "block"
    assert end["status"] == "finished" and end["win_reason"] == "ko"
    config = await db_session.get(GameConfig, 1)
    assert end["reward_coins"] == config.mordoboi_reward_win + config.mordoboi_reward_ko_bonus
    assert end["rating_delta"] == 3
    db_session.expire_all()
    fresh = await get_user_by_telegram_id(db_session, 980006)
    assert fresh.mordoboi_rating == 3 and fresh.mordoboi_rewarded_attempts_today == 1
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.user_id == fresh.id, CoinTransaction.type == TransactionType.mordoboi_reward)
    )).scalars().all()
    assert len(txs) == 1


async def test_points_finish_rewards_once(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=2)
    headers, user, _ = await _player(client, db_session, bot_token, 980007)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    match = (await _pick(client, headers, match, "block")).json()
    end = (await _pick(client, headers, match, "block")).json()
    assert end["status"] == "finished" and end["win_reason"] in ("points", "ko")
    assert len(end["scorecards"]) == 1
    # A replay of the finishing pick changes nothing.
    again = await client.post(f"{API}/matches/{match['id']}/pick", headers=headers, json={"action": "block", "version": match["version"]})
    assert again.status_code == 200 and again.json()["reward_coins"] == end["reward_coins"]
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.mordoboi_reward)
    )).scalars().all()
    assert len(txs) == 1


async def test_retried_pick_is_idempotent_and_stale_version_is_rejected(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980008)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    first = (await _pick(client, headers, match, "hook")).json()
    retry = await _pick(client, headers, match, "hook")  # same version, same action
    assert retry.status_code == 200
    assert len(retry.json()["log"]) == 1 and retry.json()["version"] == first["version"]
    stale = await _pick(client, headers, match, "jab")  # old version, new action
    assert stale.status_code == 409 and stale.json()["error"]["details"]["version"] == first["version"]
    db_match = await _load_match(db_session, match["id"])
    assert len(db_match.server_state["log"]) == 1


async def test_unaffordable_action_is_refused(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980009)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await _rewrite_state(db_session, match["id"], lambda s: s["fighters"]["user"].update(stamina=2))
    fresh = (await client.get(f"{API}/matches/{match['id']}", headers=headers)).json()
    assert fresh["available_actions"] == ["block"]
    assert (await _pick(client, headers, fresh, "uppercut")).status_code == 409


async def test_forfeit_is_a_loss_without_reward(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980010)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    end = (await client.post(f"{API}/matches/{match['id']}/forfeit", headers=headers)).json()
    assert end["result"] == "loss" and end["win_reason"] == "forfeit" and end["reward_coins"] == 0
    assert (await client.post(f"{API}/matches/{match['id']}/forfeit", headers=headers)).status_code == 409


async def test_abandoned_bot_bout_is_lost(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980011)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    await _rewrite_state(db_session, match["id"], lambda s: s.update(last_activity_at=old))
    after = (await client.get(f"{API}/matches/{match['id']}", headers=headers)).json()
    assert after["status"] == "finished" and after["result"] == "loss" and after["win_reason"] == "timeout"


# ---------------------------------------------------------------------------
# Limits and rewards
# ---------------------------------------------------------------------------

async def test_one_active_bout_and_hourly_limit(client, db_session, bot_token):
    await _set_config(db_session, hourly_game_limit=2)
    headers, _, _ = await _player(client, db_session, bot_token, 980020)
    first = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert (await client.post(f"{API}/matches/bot", headers=headers)).status_code == 409
    await client.post(f"{API}/matches/{first['id']}/forfeit", headers=headers)
    second = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    await client.post(f"{API}/matches/{second['id']}/forfeit", headers=headers)
    third = await client.post(f"{API}/matches/bot", headers=headers)
    assert third.status_code == 409 and "retry_after_seconds" in third.json()["error"]["details"]
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["mordoboi"] == 0 and "mordoboi" in limits["resets_at"]


async def test_daily_reward_cap_and_blocked_rewards(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1, mordoboi_daily_limit=1)
    headers, user, _ = await _player(client, db_session, bot_token, 980021)
    rewards = []
    for _ in range(2):
        match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
        end = (await _pick(client, headers, match, "block")).json()
        assert end["status"] == "finished"
        rewards.append(end["reward_coins"])
    assert rewards[0] > 0 and rewards[1] == 0

    headers2, user2, _ = await _player(client, db_session, bot_token, 980022)
    user2 = await get_user_by_telegram_id(db_session, 980022)
    user2.game_rewards_blocked = True
    await db_session.commit()
    match = (await client.post(f"{API}/matches/bot", headers=headers2)).json()
    end = (await _pick(client, headers2, match, "block")).json()
    assert end["reward_coins"] == 0


async def test_easy_bot_pays_less_and_caps_rating(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1, mordoboi_bot_easy_reward_pct=50)
    headers, _, _ = await _player(client, db_session, bot_token, 980023)
    match = (await client.post(f"{API}/matches/bot", headers=headers, json={"difficulty": "easy"})).json()
    end = (await _pick(client, headers, match, "block")).json()
    config = await db_session.get(GameConfig, 1)
    full = {"win": config.mordoboi_reward_win, "draw": config.mordoboi_reward_draw, "loss": config.mordoboi_reward_loss}
    assert end["reward_coins"] == round(full[end["result"]] * 50 / 100)
    assert end["rating_delta"] <= 1


# ---------------------------------------------------------------------------
# Friend bouts: secret picks, the race of two picks, sweep, notifications
# ---------------------------------------------------------------------------

async def _friend_bout(client, db_session, bot_token, a=980030, b=980031):
    headers_a, user_a, _ = await _player(client, db_session, bot_token, a, rating=82)
    headers_b, user_b, _ = await _player(client, db_session, bot_token, b, rating=78, position=Position.RW)
    created = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})).json()
    assert created["status"] == "pending_accept"
    pending_b = (await client.get(f"{API}/matches/{created['id']}", headers=headers_b)).json()
    assert pending_b["opponent"] is None  # the challenger's boxer stays hidden until accepted
    accepted = (await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)).json()
    assert accepted["status"] == "in_progress" and accepted["deadline"] is not None
    return headers_a, headers_b, user_a, user_b, accepted


async def test_friend_picks_stay_secret_until_both_are_in(client, db_session, bot_token):
    headers_a, headers_b, _, user_b, match = await _friend_bout(client, db_session, bot_token)
    a_view = (await _pick(client, headers_a, match, "hook")).json()
    assert a_view["my_pick"] == "hook" and not a_view["can_pick"] and a_view["log"] == []
    assert a_view["version"] == match["version"]  # one pick does not move the version
    b_view = (await client.get(f"{API}/matches/{match['id']}", headers=headers_b)).json()
    assert b_view["opponent_ready"] and b_view["my_pick"] is None
    assert "hook" not in str({k: v for k, v in b_view.items() if k != "available_actions"})
    nudges = (await db_session.execute(
        select(Notification).where(Notification.user_id == user_b.id, Notification.type == NotificationType.mordoboi_your_turn)
    )).scalars().all()
    assert len(nudges) == 1 and nudges[0].related_object_type == "mordoboi_match"

    resolved = (await _pick(client, headers_b, b_view, "dodge")).json()
    assert len(resolved["log"]) == 1 and resolved["log"][0]["my_action"] == "dodge"
    assert resolved["log"][0]["opponent_action"] == "hook" and resolved["log"][0]["my_outcome"] == "counter"
    a_after = (await client.get(f"{API}/matches/{match['id']}", headers=headers_a)).json()
    assert a_after["log"][0]["my_outcome"] == "slipped" and a_after["version"] == match["version"] + 1


async def test_race_of_two_picks(client, db_session, bot_token):
    headers_a, headers_b, _, _, match = await _friend_bout(client, db_session, bot_token, 980032, 980033)
    # Same side, two different picks against the same version: the second loses.
    assert (await _pick(client, headers_a, match, "jab")).status_code == 200
    second = await _pick(client, headers_a, match, "uppercut")
    assert second.status_code == 409
    # Both sides against the same version: both count, the exchange resolves once.
    assert (await _pick(client, headers_b, match, "block")).status_code == 200
    db_match = await _load_match(db_session, match["id"])
    assert len(db_match.server_state["log"]) == 1
    assert db_match.server_state["log"][0]["actions"] == {"user": "jab", "opponent": "block"}
    # The loser of the race retrying its first pick is a no-op, not a new exchange.
    assert (await _pick(client, headers_a, match, "jab")).status_code == 200
    db_match = await _load_match(db_session, match["id"])
    assert len(db_match.server_state["log"]) == 1


async def test_missed_deadline_autopilots_then_loses_by_timeout(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_max_auto_moves=1)
    headers_a, headers_b, user_a, user_b, match = await _friend_bout(client, db_session, bot_token, 980034, 980035)
    await _pick(client, headers_a, match, "jab")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    await _rewrite_state(db_session, match["id"], lambda s: s.update(deadline=past))
    after = (await client.get(f"{API}/matches/{match['id']}", headers=headers_a)).json()
    assert len(after["log"]) == 1 and after["log"][0]["opponent_auto"] and after["status"] == "in_progress"

    await _pick(client, headers_a, after, "jab")
    await _rewrite_state(db_session, match["id"], lambda s: s.update(deadline=past))
    end = (await client.get(f"{API}/matches/{match['id']}", headers=headers_b)).json()
    assert end["status"] == "finished" and end["result"] == "loss" and end["win_reason"] == "timeout"
    assert end["reward_coins"] == 0 and end["rating_delta"] == 0  # friend bouts move no rating
    a_end = (await client.get(f"{API}/matches/{match['id']}", headers=headers_a)).json()
    assert a_end["result"] == "win" and a_end["reward_coins"] > 0


async def test_challenge_decline_cancel_and_expiry(client, db_session, bot_token):
    headers_a, user_a, _ = await _player(client, db_session, bot_token, 980036)
    headers_b, user_b, _ = await _player(client, db_session, bot_token, 980037)
    created = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})).json()
    assert (await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_a)).status_code == 403
    assert (await client.post(f"{API}/matches/{created['id']}/decline", headers=headers_b)).json()["status"] == "declined"
    second = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})).json()
    assert (await client.post(f"{API}/matches/{second['id']}/cancel", headers=headers_a)).json()["status"] == "cancelled"
    third = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})).json()
    m = await _load_match(db_session, third["id"])
    m.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    listed = (await client.get(f"{API}/matches", headers=headers_b)).json()
    assert next(x for x in listed if x["id"] == third["id"])["status"] == "expired"


async def test_finished_friend_bout_notifies_both(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1)
    headers_a, headers_b, user_a, user_b, match = await _friend_bout(client, db_session, bot_token, 980038, 980039)
    await _pick(client, headers_a, match, "block")
    end = (await _pick(client, headers_b, match, "block")).json()
    assert end["status"] == "finished" and end["result"] == "draw"
    for uid in (user_a.id, user_b.id):
        rows = (await db_session.execute(
            select(Notification).where(Notification.user_id == uid, Notification.type == NotificationType.mordoboi_match_finished)
        )).scalars().all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# Matchmaking
# ---------------------------------------------------------------------------

async def test_matchmaking_pairs_two_searchers_live(client, db_session, bot_token):
    headers_a, _, _ = await _player(client, db_session, bot_token, 980040)
    headers_b, _, _ = await _player(client, db_session, bot_token, 980041)
    assert (await client.post(f"{API}/matchmaking/search", headers=headers_a)).json()["status"] == "searching"
    assert (await client.get(f"{API}/matchmaking/status", headers=headers_a)).json()["status"] == "searching"
    assert (await client.post(f"{API}/matchmaking/search", headers=headers_b)).status_code == 200
    status_b = (await client.get(f"{API}/matchmaking/status", headers=headers_b)).json()
    assert status_b["status"] == "matched"
    status_a = (await client.get(f"{API}/matchmaking/status", headers=headers_a)).json()
    assert status_a == status_b
    match = (await client.get(f"{API}/matches/{status_a['match_id']}", headers=headers_a)).json()
    assert match["opponent_type"] == "online" and match["live"] and match["deadline"] is not None


async def test_stats_and_ranking(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 980042)
    stats = (await client.get(f"{API}/stats", headers=headers)).json()
    assert stats["mordoboi_rating"] == 0
    ranking = await client.get("/api/v1/leaderboard/ranking?metric=mordoboi_rating", headers=headers)
    assert ranking.status_code == 200


# ---------------------------------------------------------------------------
# Open (chat-link) challenges with stakes
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("stake_guards_off")
async def test_open_challenge_with_stake_pays_the_pot(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1)
    headers_a, user_a, _ = await _player(client, db_session, bot_token, 980050)
    headers_b, user_b, _ = await _player(client, db_session, bot_token, 980051)
    start_a, start_b = user_a.balance, user_b.balance
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers_a, json={"stake_coins": 100})).json()
    assert created["opponent_type"] == "chat" and created["stake_coins"] == 100 and created["status"] == "pending_accept"
    preview = (await client.get(f"{API}/matches/open/{created['id']}", headers=headers_b)).json()
    assert preview["stake_coins"] == 100 and not preview["is_own_challenge"] and preview["status"] == "pending_accept"
    assert (await client.get(f"{API}/matches/open/{created['id']}", headers=headers_a)).json()["is_own_challenge"]
    assert (await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_a)).status_code == 409

    match = (await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_b)).json()
    assert match["status"] == "in_progress" and match["viewer_side"] == "opponent" and match["deadline"]
    again = await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_b)
    assert again.status_code == 409  # one acceptor, stakes debited once

    # Both block the only exchange: an even bout, a draw, stakes refunded.
    await _pick(client, headers_a, match, "block")
    end = (await _pick(client, headers_b, match, "block")).json()
    assert end["status"] == "finished" and end["result"] == "draw"
    db_session.expire_all()
    a = await get_user_by_telegram_id(db_session, 980050)
    b = await get_user_by_telegram_id(db_session, 980051)
    config = await db_session.get(GameConfig, 1)
    assert a.balance == start_a + config.mordoboi_reward_draw and b.balance == start_b + config.mordoboi_reward_draw


@pytest.mark.usefixtures("stake_guards_off")
async def test_forfeit_in_staked_bout_gives_the_pot_to_the_other_side(client, db_session, bot_token):
    headers_a, user_a, _ = await _player(client, db_session, bot_token, 980052)
    headers_b, user_b, _ = await _player(client, db_session, bot_token, 980053)
    start_a, start_b = user_a.balance, user_b.balance
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers_a, json={"stake_coins": 50})).json()
    await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_b)
    end = (await client.post(f"{API}/matches/{created['id']}/forfeit", headers=headers_b)).json()
    assert end["result"] == "loss" and end["reward_coins"] == 0
    db_session.expire_all()
    a = await get_user_by_telegram_id(db_session, 980052)
    b = await get_user_by_telegram_id(db_session, 980053)
    config = await db_session.get(GameConfig, 1)
    assert b.balance == start_b - 50
    assert a.balance == start_a + 50 + config.mordoboi_reward_win
    stakes = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.mordoboi_stake_lock)
    )).scalars().all()
    assert len([t for t in stakes if t.user_id in (a.id, b.id)]) == 2


async def test_open_challenge_rejects_unaffordable_stake_and_can_be_cancelled(client, db_session, bot_token):
    headers, user, _ = await _player(client, db_session, bot_token, 980054)
    await _set_config(db_session, stake_max_coins=10_000_000, trade_send_min_account_age_days=0, trade_send_min_active_days=0)
    too_much = await client.post(f"{API}/matches/open-challenge", headers=headers, json={"stake_coins": user.balance + 1})
    assert too_much.status_code == 409
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers, json={"stake_coins": 0})).json()
    assert (await client.post(f"{API}/matches/{created['id']}/cancel", headers=headers)).json()["status"] == "cancelled"
    other_headers, _, _ = await _player(client, db_session, bot_token, 980055)
    assert (await client.post(f"{API}/matches/open/{created['id']}/accept", headers=other_headers)).status_code == 409


async def test_open_challenge_expires_unaccepted(client, db_session, bot_token):
    headers_a, _, _ = await _player(client, db_session, bot_token, 980056)
    headers_b, _, _ = await _player(client, db_session, bot_token, 980057)
    created = (await client.post(f"{API}/matches/open-challenge", headers=headers_a, json={"stake_coins": 0})).json()
    m = await _load_match(db_session, created["id"])
    m.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    assert (await client.get(f"{API}/matches/open/{created['id']}", headers=headers_b)).json()["status"] == "expired"
    assert (await client.post(f"{API}/matches/open/{created['id']}/accept", headers=headers_b)).status_code == 409


# ---------------------------------------------------------------------------
# «Бруталити» and sharing a win
# ---------------------------------------------------------------------------

async def _brutality(db_session, style_key="underpants", name="Труханы на голову", coins=500):
    from app.models.monetization import Cosmetic

    item = Cosmetic(kind="brutality", name=name, style_key=style_key, coins_price=coins, stars_price=0, win_bonus_coins=10)
    db_session.add(item)
    await db_session.commit()
    return item.id


async def _won_friend_bout(client, db_session, bot_token, a, b):
    """A friend bout the challenger (a) has won by KO."""
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1)
    headers_a, headers_b, user_a, user_b, match = await _friend_bout(client, db_session, bot_token, a, b)
    ids = (user_a.id, user_b.id)
    await _rewrite_state(db_session, match["id"], _ko_ready)
    await _pick(client, headers_a, match, "jab")
    end = (await _pick(client, headers_b, match, "block")).json()
    assert end["result"] == "loss"
    won = (await client.get(f"{API}/matches/{match['id']}", headers=headers_a)).json()
    assert won["result"] == "win" and won["can_brutality"]
    assert end["can_brutality"] is False
    return headers_a, headers_b, ids[0], ids[1], won


async def test_brutality_is_bought_in_the_style_shop_and_applied_once_by_the_winner(client, db_session, bot_token):
    item_id = await _brutality(db_session)
    headers_a, headers_b, _, user_b_id, match = await _won_friend_bout(client, db_session, bot_token, 980060, 980061)
    url = f"{API}/matches/{match['id']}/brutality"

    not_owned = await client.post(url, headers=headers_a, json={"cosmetic_id": item_id})
    assert not_owned.status_code == 409

    catalog = (await client.get("/api/v1/cosmetics", headers=headers_a)).json()
    assert any(i["id"] == item_id and i["kind"] == "brutality" for i in catalog["items"])
    bought = await client.post(f"/api/v1/cosmetics/{item_id}/buy", headers=headers_a)
    assert bought.status_code == 200
    assert (await client.post("/api/v1/cosmetics/equip", headers=headers_a, json={"kind": "brutality", "cosmetic_id": item_id})).status_code == 409

    assert (await client.post(url, headers=headers_b, json={"cosmetic_id": item_id})).status_code == 409  # the loser can't
    before = (await client.get("/api/v1/profile/me", headers=headers_a)).json()["balance"]
    done = (await client.post(url, headers=headers_a, json={"cosmetic_id": item_id})).json()
    assert done["brutality"]["by_me"] and done["brutality"]["text"] == "надел ему труханы на голову"
    assert done["brutality"]["bonus_coins"] == 10 and done["reward_coins"] == match["reward_coins"] + 10
    assert (await client.get("/api/v1/profile/me", headers=headers_a)).json()["balance"] == before + 10
    assert done["can_brutality"] is False and done["version"] == match["version"] + 1
    assert (await client.post(url, headers=headers_a, json={"cosmetic_id": item_id})).status_code == 409  # once

    seen_by_loser = (await client.get(f"{API}/matches/{match['id']}", headers=headers_b)).json()
    assert seen_by_loser["brutality"]["text"] == "надел тебе труханы на голову" and not seen_by_loser["brutality"]["by_me"]
    notes = (await db_session.execute(
        select(Notification).where(Notification.user_id == user_b_id, Notification.type == NotificationType.mordoboi_brutality)
    )).scalars().all()
    assert len(notes) == 1 and "труханы" in notes[0].body


async def test_brutality_only_after_a_finished_bout(client, db_session, bot_token):
    item_id = await _brutality(db_session, style_key="fart", name="Газовая атака")
    headers, user, _ = await _player(client, db_session, bot_token, 980062)
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert (await client.post(f"{API}/matches/{match['id']}/brutality", headers=headers, json={"cosmetic_id": item_id})).status_code == 409


async def test_share_a_win_with_brutality_and_a_play_me_link(client, db_session, bot_token):
    item_id = await _brutality(db_session)
    headers_a, headers_b, user_a_id, _, match = await _won_friend_bout(client, db_session, bot_token, 980063, 980064)
    await client.post(f"/api/v1/cosmetics/{item_id}/buy", headers=headers_a)
    await client.post(f"{API}/matches/{match['id']}/brutality", headers=headers_a, json={"cosmetic_id": item_id})

    shared = (await client.post("/api/v1/share/prepare", headers=headers_a, json={"kind": "mordoboi_win", "id": match["id"]})).json()
    assert "Я победил игрока" in shared["caption"] and "сделал ему Бруталити: надел ему труханы на голову" in shared["caption"]
    assert shared["link"].endswith(f"start=mordoboi_vs_{user_a_id}")
    loser = await client.post("/api/v1/share/prepare", headers=headers_b, json={"kind": "mordoboi_win", "id": match["id"]})
    assert loser.status_code == 409


def test_brutality_phrases_read_right_from_both_sides():
    from app.services import mordoboi_brutality as b

    assert b.phrase("chicken", "Курица", False) == "заставил его кудахтать курицей на весь стадион"
    assert b.phrase("chicken", "Курица", True) == "заставил тебя кудахтать курицей на весь стадион"
    assert b.phrase("bucket", "Ведро", False) == "вылил на него ведро ледяной воды"
    assert b.phrase("baby_song", "Колыбельная", True).endswith("пока ты лежал")
    assert b.phrase("unknown", "Сюрприз", False) == "сделал ему «Сюрприз»"
    assert all(key in b.BRUTALITIES for key, *_ in b.SEED)
    assert sum(1 for *_, coins, stars, _ in b.SEED if coins) == 1
    assert all(stars >= 100 for *_, coins, stars, _ in b.SEED if not coins)


async def test_admin_uploads_a_picture_for_a_brutality(client, db_session, bot_token):
    import io

    from PIL import Image

    item_id = await _brutality(db_session)
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    admin = {"Authorization": f"Bearer {resp.json()['admin_token']}"}
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 50, 50)).save(buf, format="PNG")
    up = await client.post(
        f"/api/v1/admin/cosmetics/{item_id}/image", headers=admin,
        files={"file": ("b.png", buf.getvalue(), "image/png")},
    )
    assert up.status_code == 200 and up.json()["image_path"].startswith("cosmetics/uploads/")
    edited = await client.put(f"/api/v1/admin/cosmetics/{item_id}", headers=admin, json={
        "kind": "brutality", "name": "Труханы", "style_key": "underpants", "stars_price": 100, "win_bonus_coins": 25,
    })
    assert edited.json()["win_bonus_coins"] == 25 and edited.json()["image_path"] == up.json()["image_path"]
    gone = await client.delete(f"/api/v1/admin/cosmetics/{item_id}/image", headers=admin)
    assert gone.json()["image_path"] is None
