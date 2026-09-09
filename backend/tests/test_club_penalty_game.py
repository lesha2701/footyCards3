import pytest_asyncio

from app.models.enums import Position
from tests.factories import create_player
from tests.utils import telegram_headers


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    """club_service.create_club seeds a starting squad on every club creation — give
    every test in this file enough active players per formation category to draw from,
    mirroring test_clubs.py's identical fixture (see its docstring for the full rationale)."""
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _create_club_and_join(client, bot_token, telegram_id, name):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _first_club_card_id(client, headers) -> int:
    resp = await client.get("/api/v1/clubs/me/cards", headers=headers)
    assert resp.status_code == 200
    cards = resp.json()
    assert cards, "expected create_club's auto-seeded starting squad to give at least one club card"
    return cards[0]["id"]


async def test_penalty_start_requires_club_membership(client, bot_token):
    headers = telegram_headers(764001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": 1})
    assert resp.status_code == 404


async def test_penalty_start_rejects_a_card_from_another_club(client, bot_token):
    _, headers_a = await _create_club_and_join(client, bot_token, 764002, "Клуб А")
    other_card_id = await _first_club_card_id(client, headers_a)

    _, headers_b = await _create_club_and_join(client, bot_token, 764003, "Клуб Б")
    resp = await client.post(
        "/api/v1/clubs/me/penalty/start", headers=headers_b, json={"club_card_id": other_card_id}
    )
    assert resp.status_code == 404


async def test_penalty_full_shootout_reaches_a_result_and_credits_club_budget(client, bot_token):
    club, headers = await _create_club_and_join(client, bot_token, 764004, "Пенальти Клуб")
    card_id = await _first_club_card_id(client, headers)

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    is_finished = False
    result = None
    for _ in range(40):  # regulation (10) + generous sudden-death headroom
        kick = await client.post(
            f"/api/v1/clubs/me/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"}
        )
        assert kick.status_code == 200
        body = kick.json()
        if body["is_finished"]:
            is_finished = True
            result = body["result"]
            break
    assert is_finished
    assert result in ("win", "loss")

    claim = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    claim_body = claim.json()
    assert claim_body["result"] == result
    assert claim_body["reward_coins"] > 0

    club_resp = await client.get("/api/v1/clubs/me", headers=headers)
    assert club_resp.status_code == 200
    assert club_resp.json()["budget"] == club["budget"] + claim_body["reward_coins"]


async def test_penalty_forfeit_mid_match_counts_as_a_loss(client, bot_token):
    _, headers = await _create_club_and_join(client, bot_token, 764005, "Форфейт Клуб")
    card_id = await _first_club_card_id(client, headers)

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    session_id = start.json()["session_id"]

    forfeit = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/forfeit", headers=headers)
    assert forfeit.status_code == 200
    assert forfeit.json()["result"] == "loss"

    kick_after_forfeit = await client.post(
        f"/api/v1/clubs/me/penalty/{session_id}/kick", headers=headers, json={"direction": "top_left"}
    )
    assert kick_after_forfeit.status_code == 409


async def test_penalty_claim_credits_club_budget_not_player_coins(client, db_session, bot_token):
    from tests.factories import get_user_by_telegram_id

    club, headers = await _create_club_and_join(client, bot_token, 764006, "Кошелёк Клуб")
    card_id = await _first_club_card_id(client, headers)
    user = await get_user_by_telegram_id(db_session, 764006)
    balance_before = user.balance
    budget_before = club["budget"]

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    session_id = start.json()["session_id"]
    forfeit = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/forfeit", headers=headers)
    assert forfeit.status_code == 200

    claim = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    reward = claim.json()["reward_coins"]
    assert reward > 0
    assert claim.json()["new_club_budget"] == budget_before + reward

    await db_session.refresh(user)
    assert user.balance == balance_before  # reward goes to the club, never the player's own coins

    second_claim = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_penalty_hourly_limit_blocks_after_one_start(client, db_session, bot_token):
    from datetime import timedelta

    from tests.factories import get_user_by_telegram_id

    _, headers = await _create_club_and_join(client, bot_token, 764007, "Лимит Клуб")
    card_id = await _first_club_card_id(client, headers)

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["hourly_limit"] == 1
    assert details["retry_after_seconds"] > 0

    user = await get_user_by_telegram_id(db_session, 764007)
    user.club_penalty_hour_started_at = user.club_penalty_hour_started_at - timedelta(hours=2)
    db_session.add(user)
    await db_session.commit()

    resp = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    assert resp.status_code == 200


async def test_penalty_daily_reward_cap_still_allows_play_with_zero_reward(client, db_session, bot_token):
    from datetime import datetime, timezone

    from app.services.game_config_service import get_config
    from tests.factories import get_user_by_telegram_id

    _, headers = await _create_club_and_join(client, bot_token, 764008, "Дневной Лимит Клуб")
    card_id = await _first_club_card_id(client, headers)
    user = await get_user_by_telegram_id(db_session, 764008)

    config = await get_config(db_session)
    daily_limit = config.club_penalty_daily_reward_limit
    user.club_penalty_rewarded_attempts_today = daily_limit
    user.club_penalty_attempts_reset_at = datetime.now(timezone.utc)
    db_session.add(user)
    await db_session.commit()

    start = await client.post("/api/v1/clubs/me/penalty/start", headers=headers, json={"club_card_id": card_id})
    session_id = start.json()["session_id"]
    await client.post(f"/api/v1/clubs/me/penalty/{session_id}/forfeit", headers=headers)

    claim = await client.post(f"/api/v1/clubs/me/penalty/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == 0
    assert claim.json()["daily_cap_reached"] is True

    await db_session.refresh(user)
    assert user.club_penalty_rewarded_attempts_today == daily_limit
