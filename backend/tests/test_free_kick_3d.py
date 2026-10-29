from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

import app.core.rate_limit as rate_limit_module

from app.models.game import GameSession
from app.services import free_kick_3d_engine as engine
from app.services.free_kick_service import score_3d_shot, streak_bonus
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.test_free_kick import _grant_card, _register
from tests.utils import telegram_headers

SWIPE = {"dx": 50, "dy": -300, "curve": 40, "duration_ms": 180}


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    # The limiter is in-process and user ids repeat across tests: a series of
    # starts in one test must not 429 the next one.
    rate_limit_module._hits.clear()
    yield
    rate_limit_module._hits.clear()


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
    streak = 0
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
        streak = streak + 1 if replay.outcome == "goal" else 0
        coins += streak_bonus(config, streak) if replay.outcome == "goal" else 0
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


# --- Paid refills of the series -------------------------------------------------

from app.config import get_settings  # noqa: E402
from app.services import stars_payment_service  # noqa: E402

INTERNAL_HEADERS = {"X-Internal-Secret": get_settings().internal_api_secret}


async def _fake_invoice_link(payload_token, title, description, stars_amount, subscription_period=None):
    return f"https://t.me/invoice/{payload_token}"


async def _buy_with_stars(client, headers, telegram_id: int, charge: str):
    invoice = await client.post("/api/v1/games/free-kick-3d/refill/stars-invoice", headers=headers)
    assert invoice.status_code == 200, invoice.text
    body = invoice.json()
    pre = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": body["payload_token"], "total_amount": body["stars_amount"]}, headers=INTERNAL_HEADERS,
    )
    assert pre.json()["ok"] is True, pre.json()
    deliver = {
        "payload_token": body["payload_token"], "telegram_user_id": telegram_id,
        "telegram_payment_charge_id": charge, "total_amount": body["stars_amount"],
    }
    first = await client.post("/api/v1/internal/stars-payments/deliver", json=deliver, headers=INTERNAL_HEADERS)
    assert first.status_code == 200, first.text
    # Telegram may redeliver: still one series.
    again = await client.post("/api/v1/internal/stars-payments/deliver", json=deliver, headers=INTERNAL_HEADERS)
    assert again.status_code == 200
    return body


async def _start(client, headers, card_id):
    return await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card_id})


async def test_refills_first_for_coins_then_stars_up_to_the_daily_cap(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    user = await _register(client, db_session, 850010, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850010, bot_token)

    # The hour's series is free: nothing to refill.
    status = (await client.get("/api/v1/games/free-kick-3d/refill", headers=headers)).json()
    assert status["can_refill"] is False and status["on_cooldown"] is False
    assert (await client.post("/api/v1/games/free-kick-3d/refill", headers=headers)).status_code == 409

    assert (await _start(client, headers, card.id)).status_code == 200
    status = (await client.get("/api/v1/games/free-kick-3d/refill", headers=headers)).json()
    assert status["can_refill"] is True and status["on_cooldown"] is True
    assert status["price_coins"] == 200 and status["price_stars"] is None
    assert status["retry_after_seconds"] > 0

    # The day's first: 200 coins, a banked series, playable at once.
    before = (await get_user_by_telegram_id(db_session, 850010)).balance
    refill = await client.post("/api/v1/games/free-kick-3d/refill", headers=headers)
    assert refill.status_code == 200, refill.text
    assert refill.json()["new_balance"] == before - 200
    assert refill.json()["bonus_series"] == 1 and refill.json()["can_refill"] is False
    limits = (await client.get("/api/v1/games/limits", headers=headers)).json()
    assert limits["free_kick"] == 1 and "free_kick" not in limits["resets_at"]
    assert (await _start(client, headers, card.id)).status_code == 200

    # Then Stars only, 2 each, while on cooldown with nothing banked.
    status = (await client.get("/api/v1/games/free-kick-3d/refill", headers=headers)).json()
    assert status["price_coins"] is None and status["price_stars"] == 2 and status["refills_today"] == 1
    assert (await client.post("/api/v1/games/free-kick-3d/refill", headers=headers)).status_code == 409
    for i in range(4):
        await _buy_with_stars(client, headers, 850010, f"fk-refill-{i}")
        assert (await _start(client, headers, card.id)).status_code == 200

    # Five today: the cap.
    status = (await client.get("/api/v1/games/free-kick-3d/refill", headers=headers)).json()
    assert status["refills_today"] == 5 and status["can_refill"] is False
    assert (await client.post("/api/v1/games/free-kick-3d/refill/stars-invoice", headers=headers)).status_code == 409
    assert (await _start(client, headers, card.id)).status_code == 409
    # Stars never touched the coin balance: only the one coin refill did.
    fresh = await get_user_by_telegram_id(db_session, 850010)
    await db_session.refresh(fresh)
    assert fresh.balance == before - 200


async def test_refill_needs_the_coins(client, db_session, bot_token):
    user = await _register(client, db_session, 850011, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850011, bot_token)
    assert (await _start(client, headers, card.id)).status_code == 200
    user = await get_user_by_telegram_id(db_session, 850011)
    user.balance = 50
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/games/free-kick-3d/refill", headers=headers)
    assert resp.status_code in (400, 402, 409)
    await db_session.refresh(user)
    assert user.balance == 50 and user.free_kick_bonus_series == 0


async def test_stars_refill_pre_checkout_refuses_past_the_cap(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    user = await _register(client, db_session, 850012, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(850012, bot_token)
    assert (await _start(client, headers, card.id)).status_code == 200
    assert (await client.post("/api/v1/games/free-kick-3d/refill", headers=headers)).status_code == 200
    assert (await _start(client, headers, card.id)).status_code == 200

    # An invoice opened while allowed, paid only after the cap was reached elsewhere.
    invoice = (await client.post("/api/v1/games/free-kick-3d/refill/stars-invoice", headers=headers)).json()
    user = await get_user_by_telegram_id(db_session, 850012)
    user.free_kick_refills_today = 5
    db_session.add(user)
    await db_session.commit()
    pre = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout",
        json={"payload_token": invoice["payload_token"], "total_amount": invoice["stars_amount"]}, headers=INTERNAL_HEADERS,
    )
    assert pre.json()["ok"] is False


def test_streak_bonus_on_the_3rd_5th_10th_and_every_10th():
    cfg = SimpleNamespace(free_kick_streak_3_bonus=15, free_kick_streak_5_bonus=40, free_kick_streak_10_bonus=120)
    assert [streak_bonus(cfg, n) for n in range(1, 12)] == [0, 0, 15, 0, 40, 0, 0, 0, 0, 120, 0]
    assert streak_bonus(cfg, 20) == 120 and streak_bonus(cfg, 25) == 0


def _swipe_for(seed: int, rating: int, outcome: str) -> dict:
    setup = engine.create_setup(seed, rating)
    for dy in range(-200, -620, -20):
        for dx in range(-200, 201, 10):
            for curve in (0, 60, -60):
                if engine.simulate_shot(setup, engine.Swipe(dx, dy, curve, 160)).outcome == outcome:
                    return {"dx": dx, "dy": dy, "curve": curve, "duration_ms": 160}
    raise AssertionError(f"no {outcome} for seed {seed}")


async def test_goals_in_a_row_pay_the_streak_bonus_and_a_miss_resets_it(client, db_session, bot_token):
    user = await _register(client, db_session, 850020, bot_token)
    card = await _grant_card(db_session, user.id, rating=80)
    headers = telegram_headers(850020, bot_token)
    user.free_kick_goal_streak = 2
    db_session.add(user)
    await db_session.commit()
    config = await get_config(db_session)

    start = (await client.post("/api/v1/games/free-kick-3d/start", headers=headers, json={"user_card_id": card.id})).json()
    assert start["streak"] == 2
    sid = start["session_id"]
    kick = await _age_current_kick(db_session, sid)
    goal = (await client.post(f"/api/v1/games/free-kick-3d/{sid}/shot", headers=headers, json=_swipe_for(kick["seed"], 80, "goal"))).json()
    assert goal["outcome"] == "goal"
    assert (goal["streak"], goal["streak_bonus"]) == (3, config.free_kick_streak_3_bonus)
    assert goal["coins_this_kick"] >= config.free_kick_3d_goal_coins + config.free_kick_streak_3_bonus

    kick = await _age_current_kick(db_session, sid)
    miss = (await client.post(f"/api/v1/games/free-kick-3d/{sid}/shot", headers=headers, json=_swipe_for(kick["seed"], 80, "miss"))).json()
    assert (miss["streak"], miss["streak_bonus"]) == (0, 0)
    await db_session.refresh(user)
    assert user.free_kick_goal_streak == 0
