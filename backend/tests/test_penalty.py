from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.services.penalty_service import player_miss_chance
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _grant_card(db_session, owner_id: int, rating: int = 80) -> UserCard:
    player = await create_player(db_session, rarity=Rarity.rare, rating=rating)
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.flush()
    card.serial_number = card.id
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


def test_player_miss_chance_decreases_with_rating():
    assert player_miss_chance(58) > player_miss_chance(99)
    assert round(player_miss_chance(58), 2) == 0.30
    assert round(player_miss_chance(99), 2) == 0.05


async def test_penalty_start_rejects_card_not_owned_by_user(client, db_session, bot_token):
    await _register(client, db_session, 830001, bot_token)
    other_user = await _register(client, db_session, 830002, bot_token)
    other_card = await _grant_card(db_session, other_user.id)

    headers = telegram_headers(830001, bot_token)
    resp = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": other_card.id})
    assert resp.status_code == 403


async def test_penalty_full_shootout_resolves_and_pays_reward(client, db_session, bot_token):
    user = await _register(client, db_session, 830003, bot_token)
    card = await _grant_card(db_session, user.id, rating=99)  # near-zero miss chance for a deterministic test
    headers = telegram_headers(830003, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200
    assert start.json()["first_kicker"] == "player"
    session_id = start.json()["session_id"]

    is_finished = False
    result = None
    for _ in range(30):  # regulation (10 kicks) + a safety margin for sudden death
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})
        assert resp.status_code == 200
        body = resp.json()
        is_finished = body["is_finished"]
        result = body["result"]
        if is_finished:
            break

    assert is_finished
    assert result in ("win", "loss")

    claim = await client.post(f"/api/v1/games/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["result"] == result

    second_claim = await client.post(f"/api/v1/games/penalty/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_penalty_invalid_direction_rejected(client, db_session, bot_token):
    user = await _register(client, db_session, 830004, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830004, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]

    resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "up"})
    assert resp.status_code == 409


async def test_penalty_accepts_all_six_zones(client, db_session, bot_token):
    user = await _register(client, db_session, 830006, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830006, bot_token)

    from app.services.game_config_service import get_config
    config = await get_config(db_session)
    config.hourly_game_limit = 10
    db_session.add(config)
    await db_session.commit()

    zones = ["top_left", "top_center", "top_right", "bottom_left", "bottom_center", "bottom_right"]
    for i, zone in enumerate(zones):
        start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
        session_id = start.json()["session_id"]
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": zone})
        assert resp.status_code == 200, f"zone {zone} rejected"
        if i < len(zones) - 1:
            await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})


async def test_penalty_rejects_stale_three_direction_values(client, db_session, bot_token):
    user = await _register(client, db_session, 830007, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830007, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]
    resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "left"})
    assert resp.status_code == 409


async def test_penalty_bot_match_updates_penalty_rating(client, db_session, bot_token):
    """The spec requires penalty_rating to move for bot matches too (win
    +3 / loss -1, same deltas Tactico uses), not just PvP — this is the
    only place in the codebase that finishes a solo Penalty match, so the
    rating update has to live in resolve_kick's is_finished branch."""
    user = await _register(client, db_session, 830008, bot_token)
    card = await _grant_card(db_session, user.id, rating=99)  # near-zero miss chance, deterministic
    headers = telegram_headers(830008, bot_token)

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    session_id = start.json()["session_id"]

    result = None
    for _ in range(30):
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"})
        body = resp.json()
        if body["is_finished"]:
            result = body["result"]
            break

    await db_session.refresh(user)
    assert user.penalty_rating == (3 if result == "win" else -1)


async def test_penalty_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    """Regression: hitting the daily *reward* cap must not block starting a
    new session — only zero out the reward at claim time (players can keep
    playing for fun/practice once they've earned their daily coins)."""
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config

    user = await _register(client, db_session, 830005, bot_token)
    card = await _grant_card(db_session, user.id, rating=99)
    headers = telegram_headers(830005, bot_token)

    config = await get_config(db_session)
    user.penalty_rewarded_attempts_today = config.penalty_daily_limit
    user.penalty_attempts_reset_at = datetime.now(timezone.utc)  # keep _ensure_daily_reset from wiping the cap back to 0
    db_session.add(user)
    await db_session.commit()

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    is_finished = False
    for _ in range(30):
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "bottom_right"})
        is_finished = resp.json()["is_finished"]
        if is_finished:
            break
    assert is_finished

    claim = await client.post(f"/api/v1/games/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0

    await db_session.refresh(user)
    assert user.penalty_rewarded_attempts_today == config.penalty_daily_limit  # not incremented past the cap


async def test_penalty_hourly_limit_blocks_after_three_starts(client, db_session, bot_token):
    from datetime import timedelta

    user = await _register(client, db_session, 830005, bot_token)
    card = await _grant_card(db_session, user.id)
    headers = telegram_headers(830005, bot_token)

    for _ in range(3):
        resp = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
        assert resp.status_code == 200

    resp = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 3
    assert details["retry_after_seconds"] > 0

    await db_session.refresh(user)
    user.penalty_hour_started_at = user.penalty_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 200
