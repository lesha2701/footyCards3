from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, NotificationType, Position, Rarity
from app.models.game_config import GameConfig
from app.models.notification import Notification
from app.models.user import User
from app.services import tactico_service
from app.services.card_creation import create_user_card
from app.services.tactico_service import _effective_stat, _resolve_round_winner
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, bot_token, telegram_id: int) -> dict:
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers


async def _build_squad_cards(db_session, user_id: int, count: int = 11, **overrides) -> list[int]:
    ids = []
    for _ in range(count):
        player = await create_player(db_session, **overrides)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        ids.append(card.id)
    return ids


async def _set_config(db_session, **overrides) -> None:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()


async def _fake_weak_bot_squad(db, avg_rating, difficulty, config) -> list[dict]:
    return [
        {
            "user_card_id": None, "player_id": 90000 + i, "display_name": f"Bot Player {i}",
            "position": "CM", "image_path": None, "rarity": "common",
            "rating": 40, "attack_rating": 40, "defense_rating": 40,
        }
        for i in range(11)
    ]


# ---------------------------------------------------------------------------
# Squad
# ---------------------------------------------------------------------------

async def test_set_squad_requires_exactly_11_cards(client, db_session, bot_token):
    headers = await _register(client, bot_token, 950001)
    user = await get_user_by_telegram_id(db_session, 950001)
    card_ids = await _build_squad_cards(db_session, user.id, count=5)

    resp = await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})
    assert resp.status_code == 409


async def test_set_squad_rejects_cards_owned_by_others(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 950002)
    user_a = await get_user_by_telegram_id(db_session, 950002)
    card_ids = await _build_squad_cards(db_session, user_a.id, count=11)

    headers_b = await _register(client, bot_token, 950003)
    resp = await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": card_ids})
    assert resp.status_code == 403


async def test_set_squad_success(client, db_session, bot_token):
    headers = await _register(client, bot_token, 950004)
    user = await get_user_by_telegram_id(db_session, 950004)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)

    resp = await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_complete"] is True
    assert len(body["cards"]) == 11

    resp = await client.get("/api/v1/tactico/squad", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_complete"] is True


# ---------------------------------------------------------------------------
# Phase bonus (pure function)
# ---------------------------------------------------------------------------

def test_phase_bonus_lets_lower_stat_forward_beat_higher_stat_midfielder():
    forward = {"position": "ST", "attack_rating": 70, "defense_rating": 30, "rating": 0}
    midfielder = {"position": "CM", "attack_rating": 75, "defense_rating": 75, "rating": 0}
    winner = _resolve_round_winner(forward, midfielder, "attack", 0.15)
    assert winner == "user"  # 70 * 1.15 = 80.5 > 75


def test_phase_bonus_exact_tie_is_a_draw():
    a = {"position": "CM", "attack_rating": 70, "defense_rating": 70, "rating": 0}
    b = {"position": "CM", "attack_rating": 70, "defense_rating": 70, "rating": 0}
    assert _resolve_round_winner(a, b, "attack", 0.15) == "draw"


def test_effective_stat_no_bonus_for_midfield_in_either_phase():
    assert _effective_stat("CM", 70, 65, 0, "attack", 0.15) == 70
    assert _effective_stat("CM", 70, 65, 0, "defense", 0.15) == 65


def test_effective_stat_adds_overall_rating_on_top_of_the_phase_stat():
    # Overall rating is always added in full; only the phase sub-stat gets the position bonus.
    assert _effective_stat("CM", 70, 65, 20, "attack", 0.15) == 90
    assert _effective_stat("ST", 70, 65, 20, "attack", 0.15) == 70 * 1.15 + 20


def test_overall_rating_can_swing_a_round_the_stat_alone_would_lose():
    weaker_forward_higher_rating = {"position": "ST", "attack_rating": 60, "defense_rating": 30, "rating": 90}
    stronger_stat_lower_rating = {"position": "CM", "attack_rating": 80, "defense_rating": 80, "rating": 40}
    # 60*1.15=69+90=159 vs 80+40=120 -> the higher-rated forward wins despite a lower base ATK.
    assert _resolve_round_winner(weaker_forward_higher_rating, stronger_stat_lower_rating, "attack", 0.15) == "user"


# ---------------------------------------------------------------------------
# Bot match
# ---------------------------------------------------------------------------

async def test_bot_match_full_playthrough_rewards_and_rating(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950010)
    user = await get_user_by_telegram_id(db_session, 950010)
    card_ids = await _build_squad_cards(
        db_session, user.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    resp = await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    match = resp.json()
    assert match["status"] == "in_progress"

    guard = 0
    while match["status"] == "in_progress":
        guard += 1
        assert guard < 15
        card_id = match["pickable_cards"][0]["user_card_id"]
        resp = await client.post(
            f"/api/v1/tactico/matches/{match['id']}/rounds", headers=headers, json={"user_card_id": card_id}
        )
        assert resp.status_code == 200
        match = resp.json()

    assert match["status"] == "finished"
    assert match["result"] == "win"
    assert match["user_score"] == 11
    assert match["opponent_score"] == 0
    assert match["reward_coins"] > 0
    assert match["rating_delta"] == 3

    await db_session.refresh(user)
    assert user.tactics_rating == 3
    assert user.balance >= match["reward_coins"]


# ---------------------------------------------------------------------------
# Friend match
# ---------------------------------------------------------------------------

async def test_friend_challenge_accept_and_hidden_round_submission(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")

    headers_a = await _register(client, bot_token, 950020)
    user_a = await get_user_by_telegram_id(db_session, 950020)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11, position=Position.CM, rating=70)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950021)
    user_b = await get_user_by_telegram_id(db_session, 950021)
    cards_b = await _build_squad_cards(db_session, user_b.id, count=11, position=Position.CM, rating=70)
    await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": cards_b})

    resp = await client.post(
        "/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id}
    )
    assert resp.status_code == 200
    match_id = resp.json()["id"]
    assert resp.json()["status"] == "pending_accept"

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"

    # A submits first.
    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    a_card = resp.json()["pickable_cards"][0]["user_card_id"]
    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_a, json={"user_card_id": a_card})
    assert resp.status_code == 200
    assert resp.json()["waiting_for_opponent"] is True
    assert len(resp.json()["rounds"]) == 0  # not resolved yet — B hasn't submitted

    # B's view shouldn't reveal A's pick yet, and B can still pick.
    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_b)
    b_view = resp.json()
    assert b_view["waiting_for_opponent"] is False
    assert len(b_view["rounds"]) == 0
    b_card = b_view["pickable_cards"][0]["user_card_id"]

    # B submits second (receiver-first-vs-second order covered by symmetry of A-then-B here).
    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_b, json={"user_card_id": b_card})
    assert resp.status_code == 200
    b_after = resp.json()
    assert len(b_after["rounds"]) == 1
    assert b_after["rounds"][0]["winner"] == "draw"  # identical CM cards, no phase bonus

    # Now try the opposite submission order for round 2: B submits first this time.
    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_b)
    b_card2 = resp.json()["pickable_cards"][0]["user_card_id"]
    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_b, json={"user_card_id": b_card2})
    assert resp.json()["waiting_for_opponent"] is True

    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    a_view = resp.json()
    assert len(a_view["rounds"]) == 1  # round 1 only — round 2 still pending on A
    a_card2 = a_view["pickable_cards"][0]["user_card_id"]
    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_a, json={"user_card_id": a_card2})
    assert len(resp.json()["rounds"]) == 2


async def test_friend_round_deadline_appears_and_auto_plays_tardy_side(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")

    headers_a = await _register(client, bot_token, 950025)
    user_a = await get_user_by_telegram_id(db_session, 950025)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11, position=Position.CM, rating=70)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950026)
    user_b = await get_user_by_telegram_id(db_session, 950026)
    cards_b = await _build_squad_cards(db_session, user_b.id, count=11, position=Position.CM, rating=70)
    await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": cards_b})

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]
    await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)

    # Before anyone has moved this round, no short deadline is exposed yet.
    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    assert resp.json()["round_deadline"] is None

    a_card = resp.json()["pickable_cards"][0]["user_card_id"]
    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_a, json={"user_card_id": a_card})
    assert resp.json()["round_deadline"] is not None

    # B (the tardy side) also sees the same deadline once they check the match.
    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_b)
    assert resp.json()["round_deadline"] is not None
    assert resp.json()["waiting_for_opponent"] is False

    from sqlalchemy.orm.attributes import flag_modified

    from app.models.tactico import TacticoMatch

    match = await db_session.get(TacticoMatch, match_id)
    state = dict(match.server_state)
    state["current_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)
    assert resp.status_code == 200
    assert len(resp.json()["rounds"]) == 1  # B's missed turn was auto-played from their pool


async def test_friend_match_gives_rating_only_no_coins(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")

    headers_a = await _register(client, bot_token, 950030)
    user_a = await get_user_by_telegram_id(db_session, 950030)
    cards_a = await _build_squad_cards(
        db_session, user_a.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950031)
    user_b = await get_user_by_telegram_id(db_session, 950031)
    cards_b = await _build_squad_cards(
        db_session, user_b.id, count=11, position=Position.CM, rating=20, attack_rating=1, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": cards_b})

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]
    await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)

    guard = 0
    a_view = (await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)).json()
    while a_view["status"] == "in_progress":
        guard += 1
        assert guard < 15
        if not a_view["waiting_for_opponent"]:
            card_id = a_view["pickable_cards"][0]["user_card_id"]
            await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_a, json={"user_card_id": card_id})
        b_view = (await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_b)).json()
        if b_view["status"] == "in_progress" and not b_view["waiting_for_opponent"]:
            card_id = b_view["pickable_cards"][0]["user_card_id"]
            await client.post(f"/api/v1/tactico/matches/{match_id}/rounds", headers=headers_b, json={"user_card_id": card_id})
        a_view = (await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_a)).json()

    assert a_view["status"] == "finished"
    assert a_view["result"] == "win"
    assert a_view["reward_coins"] == 0
    assert a_view["rating_delta"] == 3

    b_view = (await client.get(f"/api/v1/tactico/matches/{match_id}", headers=headers_b)).json()
    assert b_view["result"] == "loss"
    assert b_view["reward_coins"] == 0
    assert b_view["rating_delta"] == -1

    await db_session.refresh(user_a)
    await db_session.refresh(user_b)
    assert user_a.tactics_rating == 3
    assert user_b.tactics_rating == 0  # clamped at 0, started at 0 with a -1 delta


async def test_decline_challenge_notifies_sender(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 950040)
    user_a = await get_user_by_telegram_id(db_session, 950040)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950041)
    user_b = await get_user_by_telegram_id(db_session, 950041)

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/decline", headers=headers_b)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"

    result = await db_session.execute(
        select(Notification).where(
            Notification.user_id == user_a.id, Notification.type == NotificationType.tactico_challenge_declined
        )
    )
    assert result.scalar_one_or_none() is not None


async def test_cancel_challenge(client, db_session, bot_token):
    headers_a = await _register(client, bot_token, 950042)
    user_a = await get_user_by_telegram_id(db_session, 950042)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950043)
    user_b = await get_user_by_telegram_id(db_session, 950043)

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/cancel", headers=headers_a)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)
    assert resp.status_code == 409


async def test_timeout_auto_plays_overdue_round(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")

    headers_a = await _register(client, bot_token, 950050)
    user_a = await get_user_by_telegram_id(db_session, 950050)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950051)
    user_b = await get_user_by_telegram_id(db_session, 950051)
    cards_b = await _build_squad_cards(db_session, user_b.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": cards_b})

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]
    await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)

    from app.models.tactico import TacticoMatch

    match = await db_session.get(TacticoMatch, match_id)
    state = dict(match.server_state)
    state["current_deadline"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    match.server_state = state
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get("/api/v1/tactico/matches", headers=headers_a)
    assert resp.status_code == 200
    swept_match = next(m for m in resp.json() if m["id"] == match_id)
    assert len(swept_match["rounds"]) == 1  # both sides auto-played -> round resolved


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

async def test_tactics_rating_ranking_metric(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950060)
    user = await get_user_by_telegram_id(db_session, 950060)
    card_ids = await _build_squad_cards(
        db_session, user.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    while match["status"] == "in_progress":
        card_id = match["pickable_cards"][0]["user_card_id"]
        resp = await client.post(
            f"/api/v1/tactico/matches/{match['id']}/rounds", headers=headers, json={"user_card_id": card_id}
        )
        match = resp.json()

    resp = await client.get("/api/v1/leaderboard/ranking?metric=tactics_rating", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["me"] is not None
    assert body["me"]["value"] == 3


# ---------------------------------------------------------------------------
# Forfeit / abandonment
# ---------------------------------------------------------------------------

async def test_forfeit_bot_match_is_always_a_loss_even_when_winning(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950070)
    user = await get_user_by_telegram_id(db_session, 950070)
    card_ids = await _build_squad_cards(
        db_session, user.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match = resp.json()

    # Win the first round (user is far stronger), then forfeit while ahead.
    card_id = match["pickable_cards"][0]["user_card_id"]
    resp = await client.post(f"/api/v1/tactico/matches/{match['id']}/rounds", headers=headers, json={"user_card_id": card_id})
    match = resp.json()
    assert match["user_score"] >= 1

    resp = await client.post(f"/api/v1/tactico/matches/{match['id']}/forfeit", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "finished"
    assert body["result"] == "loss"
    assert body["rating_delta"] == -1


async def test_cannot_forfeit_match_that_is_not_in_progress(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950071)
    user = await get_user_by_telegram_id(db_session, 950071)
    card_ids = await _build_squad_cards(
        db_session, user.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})
    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match_id = resp.json()["id"]

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/forfeit", headers=headers)
    assert resp.status_code == 200

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/forfeit", headers=headers)
    assert resp.status_code == 409


async def test_cannot_start_new_bot_match_while_one_in_progress(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950072)
    user = await get_user_by_telegram_id(db_session, 950072)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409


async def test_cannot_challenge_while_bot_match_in_progress(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950073)
    user = await get_user_by_telegram_id(db_session, 950073)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})
    await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})

    other_headers = await _register(client, bot_token, 950074)
    other_user = await get_user_by_telegram_id(db_session, 950074)

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers, json={"receiver_id": other_user.id})
    assert resp.status_code == 409


async def test_cannot_accept_challenge_while_another_match_in_progress(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers_a = await _register(client, bot_token, 950075)
    user_a = await get_user_by_telegram_id(db_session, 950075)
    cards_a = await _build_squad_cards(db_session, user_a.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_a, json={"user_card_ids": cards_a})

    headers_b = await _register(client, bot_token, 950076)
    user_b = await get_user_by_telegram_id(db_session, 950076)
    cards_b = await _build_squad_cards(db_session, user_b.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers_b, json={"user_card_ids": cards_b})

    resp = await client.post("/api/v1/tactico/matches/challenge", headers=headers_a, json={"receiver_id": user_b.id})
    match_id = resp.json()["id"]

    # B already has a bot match in progress when the challenge arrives.
    await client.post("/api/v1/tactico/matches/bot", headers=headers_b, json={"difficulty": "medium"})

    resp = await client.post(f"/api/v1/tactico/matches/{match_id}/accept", headers=headers_b)
    assert resp.status_code == 409


async def test_abandoned_bot_match_is_auto_forfeited(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950077)
    user = await get_user_by_telegram_id(db_session, 950077)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match_id = resp.json()["id"]

    from app.models.tactico import TacticoMatch
    from sqlalchemy.orm.attributes import flag_modified

    match = await db_session.get(TacticoMatch, match_id)
    state = dict(match.server_state)
    state["last_activity_at"] = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    db_session.add(match)
    await db_session.commit()

    resp = await client.get("/api/v1/tactico/matches", headers=headers)
    assert resp.status_code == 200
    swept_match = next(m for m in resp.json() if m["id"] == match_id)
    assert swept_match["status"] == "finished"
    assert swept_match["result"] == "loss"

    await db_session.refresh(user)
    assert user.tactics_rating == 0  # clamped at 0 from a -1 delta


# ---------------------------------------------------------------------------
# Hourly play limit
# ---------------------------------------------------------------------------

async def test_hourly_limit_blocks_extra_bot_matches(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)
    await _set_config(db_session, hourly_game_limit=2)

    headers = await _register(client, bot_token, 950080)
    user = await get_user_by_telegram_id(db_session, 950080)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    for _ in range(2):
        resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
        assert resp.status_code == 200
        match_id = resp.json()["id"]
        await client.post(f"/api/v1/tactico/matches/{match_id}/forfeit", headers=headers)

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["hourly_limit"] == 2


async def test_hourly_limit_reflected_in_game_limits_endpoint(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)
    await _set_config(db_session, hourly_game_limit=5)

    headers = await _register(client, bot_token, 950083)
    user = await get_user_by_telegram_id(db_session, 950083)
    card_ids = await _build_squad_cards(db_session, user.id, count=11)
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match_id = resp.json()["id"]
    await client.post(f"/api/v1/tactico/matches/{match_id}/forfeit", headers=headers)

    resp = await client.get("/api/v1/games/limits", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["tactico"] == 4


# ---------------------------------------------------------------------------
# Squad rarity cap
# ---------------------------------------------------------------------------

async def test_set_squad_rejects_too_many_legendary_cards(client, db_session, bot_token):
    headers = await _register(client, bot_token, 950084)
    user = await get_user_by_telegram_id(db_session, 950084)
    legendary_ids = await _build_squad_cards(db_session, user.id, count=4, rarity=Rarity.legendary)
    common_ids = await _build_squad_cards(db_session, user.id, count=7, rarity=Rarity.common)

    resp = await client.put(
        "/api/v1/tactico/squad", headers=headers, json={"user_card_ids": legendary_ids + common_ids}
    )
    assert resp.status_code == 409


async def test_set_squad_rejects_too_many_epic_cards(client, db_session, bot_token):
    headers = await _register(client, bot_token, 950085)
    user = await get_user_by_telegram_id(db_session, 950085)
    epic_ids = await _build_squad_cards(db_session, user.id, count=4, rarity=Rarity.epic)
    common_ids = await _build_squad_cards(db_session, user.id, count=7, rarity=Rarity.common)

    resp = await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": epic_ids + common_ids})
    assert resp.status_code == 409


async def test_set_squad_allows_exactly_the_rarity_cap(client, db_session, bot_token):
    headers = await _register(client, bot_token, 950086)
    user = await get_user_by_telegram_id(db_session, 950086)
    legendary_ids = await _build_squad_cards(db_session, user.id, count=3, rarity=Rarity.legendary)
    common_ids = await _build_squad_cards(db_session, user.id, count=8, rarity=Rarity.common)

    resp = await client.put(
        "/api/v1/tactico/squad", headers=headers, json={"user_card_ids": legendary_ids + common_ids}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["max_legendary"] == 3
    assert body["max_epic"] == 3


# ---------------------------------------------------------------------------
# Live stats
# ---------------------------------------------------------------------------

async def test_tactico_stats_endpoint_reflects_rating_changes(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(tactico_service, "_pick_phase", lambda: "attack")
    monkeypatch.setattr(tactico_service, "_synthesize_bot_squad", _fake_weak_bot_squad)

    headers = await _register(client, bot_token, 950087)
    user = await get_user_by_telegram_id(db_session, 950087)
    card_ids = await _build_squad_cards(
        db_session, user.id, count=11, position=Position.ST, rating=90, attack_rating=99, defense_rating=1
    )
    await client.put("/api/v1/tactico/squad", headers=headers, json={"user_card_ids": card_ids})

    resp = await client.get("/api/v1/tactico/stats", headers=headers)
    assert resp.json()["tactics_rating"] == 0

    resp = await client.post("/api/v1/tactico/matches/bot", headers=headers, json={"difficulty": "medium"})
    match = resp.json()
    while match["status"] == "in_progress":
        card_id = match["pickable_cards"][0]["user_card_id"]
        resp = await client.post(
            f"/api/v1/tactico/matches/{match['id']}/rounds", headers=headers, json={"user_card_id": card_id}
        )
        match = resp.json()

    resp = await client.get("/api/v1/tactico/stats", headers=headers)
    assert resp.json()["tactics_rating"] == 3
