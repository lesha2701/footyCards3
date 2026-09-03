from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.bingo import BingoState, BingoWeek, BingoWeekGoal
from app.models.enums import BingoGoalType, Rarity
from app.models.user import User
from app.services import bingo_service
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.test_lineups_matches import _build_full_squad, _play_to_completion
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    # A brand-new user's very first /auth/session call returns before
    # last_seen_at is ever set (see _get_or_create_user's early return for
    # a just-created row) — a real client always fires more requests right
    # after, so a second call here is what actually marks the user "seen".
    resp2 = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp2.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _admin_auth(client, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)
    session_resp = await client.post("/api/v1/auth/session", headers=admin_headers)
    token = session_resp.json()["admin_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_enabling_bingo_sets_started_at_once(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)

    resp = await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    assert resp.status_code == 200
    first_started_at = resp.json()["started_at"]
    assert first_started_at is not None

    # Disabling and re-enabling must NOT move the epoch.
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": False})
    resp2 = await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    # Comparing parsed instants, not raw strings: SQLite (test DB only) drops
    # the tz suffix on a value that round-tripped through the DB even though
    # the instant itself is unchanged — Postgres preserves it.
    assert datetime.fromisoformat(resp2.json()["started_at"]).replace(tzinfo=timezone.utc) == datetime.fromisoformat(
        first_started_at.replace("Z", "+00:00")
    )


async def test_at_most_one_active_goal_per_type(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)

    resp1 = await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "packs_opened", "target_value": 1000, "is_active": True},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "packs_opened", "target_value": 500, "is_active": True},
    )
    assert resp2.status_code == 409


async def test_editing_target_mid_week_does_not_affect_current_week(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    create_resp = await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "packs_opened", "target_value": 1000, "is_active": True},
    )
    goal_id = create_resp.json()["id"]

    # Anything that reads bingo state creates+snapshots week 1.
    week = await bingo_service.get_or_create_current_week(db_session)
    week_id = week.id

    await client.put(f"/api/v1/admin/bingo/goals/{goal_id}", headers=admin_headers, json={"target_value": 1500})

    db_session.expire_all()
    snapshot = (
        await db_session.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week_id))
    ).scalar_one()
    assert snapshot.target_value == 1000  # unchanged — the edit only affects next week's snapshot


async def test_goal_added_mid_week_does_not_start_counting_until_next_week(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})

    # Week 1 starts with zero goals configured.
    week = await bingo_service.get_or_create_current_week(db_session)
    week_id = week.id

    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "trades_completed", "target_value": 10, "is_active": True},
    )

    # Incrementing now must be a no-op for the CURRENT week (no snapshot row exists for it yet).
    await bingo_service.increment_goal(db_session, BingoGoalType.trades_completed, 1)
    db_session.expire_all()
    rows = (
        await db_session.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week_id))
    ).scalars().all()
    assert rows == []


async def test_pack_open_increments_packs_opened_and_legendary_drops(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "packs_opened", "target_value": 1000, "is_active": True},
    )
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "legendary_drops", "target_value": 1000, "is_active": True},
    )
    # Week 1 must exist with these two goals snapshotted before the pack-open below.
    await bingo_service.get_or_create_current_week(db_session)

    await create_player(db_session, rarity=Rarity.legendary, rating=90)
    pack = await create_pack(db_session, "bingo_test_pack", price=100, card_count=2, probabilities={Rarity.legendary: 1.0})

    user = await _register(client, db_session, 960001, bot_token)
    headers = telegram_headers(960001, bot_token)
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200

    current = await client.get("/api/v1/bingo/current", headers=headers)
    goals = {g["goal_type"]: g["current_value"] for g in current.json()["goals"]}
    assert goals["packs_opened"] == 1
    assert goals["legendary_drops"] == 2


async def test_week_rollover_resolves_previous_week_and_creates_next(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})

    week1 = await bingo_service.get_or_create_current_week(db_session)
    assert week1.week_number == 1
    week1_id = week1.id

    # Force the epoch back 8 days so week 1 now reads as already elapsed.
    state = await db_session.get(BingoState, 1)
    state.started_at = datetime.now(timezone.utc) - timedelta(days=8)
    db_session.add(state)
    await db_session.commit()

    week2 = await bingo_service.get_or_create_current_week(db_session)
    assert week2.week_number == 2

    db_session.expire_all()
    resolved_week1 = (await db_session.execute(select(BingoWeek).where(BingoWeek.id == week1_id))).scalar_one()
    assert resolved_week1.reward_resolved is True


async def test_cannot_claim_before_all_goals_are_completed(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "trades_completed", "target_value": 1, "is_active": True},
    )
    user = await _register(client, db_session, 960004, bot_token)
    headers = telegram_headers(960004, bot_token)

    resp = await client.post("/api/v1/bingo/claim", headers=headers)
    assert resp.status_code == 409


async def test_claim_credits_coins_and_pack_and_is_visible_as_reward_preview(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "trades_completed", "target_value": 1, "is_active": True},
    )
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "bingo_reward_pack", price=100, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.put(
        "/api/v1/admin/games/config", headers=admin_headers,
        json={"bingo_reward_coins": 777, "bingo_reward_pack_id": pack.id},
    )
    assert resp.status_code == 200

    user = await _register(client, db_session, 960005, bot_token)
    user_id = user.id
    headers = telegram_headers(960005, bot_token)

    # Reward is visible as a preview even before the goal is complete.
    current = await client.get("/api/v1/bingo/current", headers=headers)
    body = current.json()
    assert body["reward_coins"] == 777
    assert body["reward_pack_name"] == "Bingo_Reward_Pack"
    assert body["has_claimed"] is False

    week = await bingo_service.get_or_create_current_week(db_session)
    goal_row = (
        await db_session.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week.id))
    ).scalar_one()
    goal_row.current_value = 1
    db_session.add(goal_row)
    await db_session.commit()

    balance_before = (await db_session.get(User, user_id)).balance

    resp = await client.post("/api/v1/bingo/claim", headers=headers)
    assert resp.status_code == 200
    claim = resp.json()
    assert claim["coins_granted"] == 777
    assert claim["granted_pack"] is not None
    assert claim["new_balance"] == balance_before + 777

    current2 = await client.get("/api/v1/bingo/current", headers=headers)
    assert current2.json()["has_claimed"] is True

    # Claiming twice is rejected.
    resp2 = await client.post("/api/v1/bingo/claim", headers=headers)
    assert resp2.status_code == 409


async def test_unclaimed_reward_is_lost_once_the_week_rolls_over(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "trades_completed", "target_value": 1, "is_active": True},
    )
    user = await _register(client, db_session, 960006, bot_token)
    headers = telegram_headers(960006, bot_token)

    week = await bingo_service.get_or_create_current_week(db_session)
    goal_row = (
        await db_session.execute(select(BingoWeekGoal).where(BingoWeekGoal.week_id == week.id))
    ).scalar_one()
    goal_row.current_value = 1
    db_session.add(goal_row)
    await db_session.commit()

    # Roll the epoch forward without ever claiming.
    state = await db_session.get(BingoState, 1)
    state.started_at = datetime.now(timezone.utc) - timedelta(days=8)
    db_session.add(state)
    await db_session.commit()
    await bingo_service.get_or_create_current_week(db_session)

    resp = await client.post("/api/v1/bingo/claim", headers=headers)
    assert resp.status_code == 409


async def test_pack_open_increments_rare_and_epic_drops_too(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "rare_drops", "target_value": 1000, "is_active": True},
    )
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "epic_drops", "target_value": 1000, "is_active": True},
    )
    await bingo_service.get_or_create_current_week(db_session)

    await create_player(db_session, rarity=Rarity.rare, rating=78)
    await create_player(db_session, rarity=Rarity.epic, rating=85)
    pack = await create_pack(
        db_session, "bingo_rare_epic_pack", price=100, card_count=4,
        probabilities={Rarity.rare: 0.5, Rarity.epic: 0.5},
    )

    user = await _register(client, db_session, 960007, bot_token)
    headers = telegram_headers(960007, bot_token)
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200
    cards = resp.json()["cards"]
    rare_count = sum(1 for c in cards if c["card"]["player"]["rarity"] == "rare")
    epic_count = sum(1 for c in cards if c["card"]["player"]["rarity"] == "epic")

    current = await client.get("/api/v1/bingo/current", headers=headers)
    goals = {g["goal_type"]: g["current_value"] for g in current.json()["goals"]}
    assert goals["rare_drops"] == rare_count
    assert goals["epic_drops"] == epic_count


async def test_penalty_forfeit_increments_penalty_matches_played(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "penalty_matches_played", "target_value": 1000, "is_active": True},
    )
    await bingo_service.get_or_create_current_week(db_session)

    from app.models.card import UserCard
    from app.models.enums import CardSource

    sender = await _register(client, db_session, 960008, bot_token)
    receiver = await _register(client, db_session, 960009, bot_token)
    sender_headers = telegram_headers(960008, bot_token)
    receiver_headers = telegram_headers(960009, bot_token)

    async def grant_card(owner_id):
        player = await create_player(db_session, rarity=Rarity.rare, rating=80)
        card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed)
        db_session.add(card)
        await db_session.flush()
        card.serial_number = card.id
        db_session.add(card)
        await db_session.commit()
        await db_session.refresh(card)
        return card

    sender_card = await grant_card(sender.id)
    receiver_card = await grant_card(receiver.id)

    challenge = await client.post(
        "/api/v1/games/penalty/challenges", headers=sender_headers,
        json={"opponent_user_id": receiver.id, "user_card_id": sender_card.id},
    )
    assert challenge.status_code == 200
    match_id = challenge.json()["id"]

    accept = await client.post(
        f"/api/v1/games/penalty/challenges/{match_id}/accept", headers=receiver_headers,
        json={"user_card_id": receiver_card.id},
    )
    assert accept.status_code == 200

    forfeit = await client.post(f"/api/v1/games/penalty/matches/{match_id}/forfeit", headers=sender_headers)
    assert forfeit.status_code == 200

    current = await client.get("/api/v1/bingo/current", headers=sender_headers)
    goals = {g["goal_type"]: g["current_value"] for g in current.json()["goals"]}
    assert goals["penalty_matches_played"] == 1


async def test_arena_match_increments_arena_matches_played(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await client.put("/api/v1/admin/bingo/state", headers=admin_headers, json={"is_enabled": True})
    await client.post(
        "/api/v1/admin/bingo/goals", headers=admin_headers,
        json={"goal_type": "arena_matches_played", "target_value": 1000, "is_active": True},
    )
    await bingo_service.get_or_create_current_week(db_session)

    headers = telegram_headers(960010, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 960010)
    slots = await _build_full_squad(db_session, user.id)
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    await _play_to_completion(client, headers)

    current = await client.get("/api/v1/bingo/current", headers=headers)
    goals = {g["goal_type"]: g["current_value"] for g in current.json()["goals"]}
    assert goals["arena_matches_played"] == 1


async def test_admin_stats_preview_counts_trailing_week_activity(client, db_session, bot_token):
    admin_headers = await _admin_auth(client, bot_token)
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "stats_preview_pack", price=100, card_count=1, probabilities={Rarity.common: 1.0})

    user = await _register(client, db_session, 960011, bot_token)
    headers = telegram_headers(960011, bot_token)
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200

    stats = await client.get("/api/v1/admin/bingo/stats-preview", headers=admin_headers)
    assert stats.status_code == 200
    counts = {item["goal_type"]: item["trailing_7d_count"] for item in stats.json()}
    assert counts["packs_opened"] >= 1
    assert "trades_completed" in counts
