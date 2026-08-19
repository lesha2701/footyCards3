import pytest

import app.core.rate_limit as rate_limit_module
from app.models.league import LeagueTier, UserLeagueRewardClaim
from app.schemas.league import LeagueTierOut, LeagueTierPublicOut


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    # The in-memory rate limiter (app/core/rate_limit.py) is process-global
    # and keyed by numeric user id, but every test gets a fresh DB whose
    # autoincrement ids restart at 1 — without this, this file's tests could
    # both contaminate and be contaminated by other test files' hits on the
    # same low-numbered bucket (e.g. "play_match:1"). Same fix already
    # applied to test_packs.py and test_lineups_matches.py in this repo.
    rate_limit_module._hits.clear()
    yield


async def test_league_tier_and_claim_round_trip(db_session):
    tier = LeagueTier(name="Дворовая лига", min_rating=0, icon="🥉", reward_coins=100, sort_order=0)
    db_session.add(tier)
    await db_session.commit()
    await db_session.refresh(tier)

    assert LeagueTierOut.model_validate(tier).reward_pack_id is None

    claim = UserLeagueRewardClaim(user_id=1, league_tier_id=tier.id, reward_coins=100)
    db_session.add(claim)
    await db_session.commit()
    await db_session.refresh(claim)
    assert claim.tier.name == "Дворовая лига"


from sqlalchemy import select

from app.models.card import UserCard
from app.models.enums import CardSource, Rarity
from app.models.player import Player
from app.models.user import User
from app.services import league_service
from app.services.card_creation import create_user_card
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def _make_user(db_session, telegram_id: int) -> User:
    user = User(telegram_id=telegram_id, balance=500)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_sync_grants_single_crossed_tier(db_session):
    tier0 = LeagueTier(name="Дворовая лига", min_rating=0, reward_coins=0, sort_order=0)
    tier1 = LeagueTier(name="Городская лига", min_rating=100, reward_coins=50, sort_order=1)
    db_session.add_all([tier0, tier1])
    await db_session.commit()

    user = await _make_user(db_session, 990001)
    user.tactics_rating = 100
    db_session.add(user)
    await db_session.commit()

    granted = await league_service.sync_league_rewards_for_user(db_session, user)
    await db_session.commit()

    assert {t.id for t in granted} == {tier0.id, tier1.id}
    await db_session.refresh(user)
    assert user.balance == 550  # 500 + 50 from tier1 (tier0 gives 0)


async def test_sync_is_idempotent(db_session):
    tier = LeagueTier(name="Дворовая лига", min_rating=0, reward_coins=20, sort_order=0)
    db_session.add(tier)
    await db_session.commit()

    user = await _make_user(db_session, 990002)

    first = await league_service.sync_league_rewards_for_user(db_session, user)
    await db_session.commit()
    second = await league_service.sync_league_rewards_for_user(db_session, user)
    await db_session.commit()

    assert len(first) == 1
    assert second == []
    await db_session.refresh(user)
    assert user.balance == 520  # only credited once


async def test_sync_multi_tier_jump_in_one_call(db_session):
    """The retroactive-rollout scenario: a user already far above several
    thresholds gets every tier they qualify for in one call."""
    tiers = [
        LeagueTier(name=f"Лига {i}", min_rating=i * 100, reward_coins=10, sort_order=i)
        for i in range(5)
    ]
    db_session.add_all(tiers)
    await db_session.commit()

    user = await _make_user(db_session, 990003)
    user.arena_rating = 250
    user.tactics_rating = 200
    db_session.add(user)
    await db_session.commit()

    granted = await league_service.sync_league_rewards_for_user(db_session, user)
    await db_session.commit()

    # total = 450 -> qualifies for tiers at 0/100/200/300/400 = all 5
    assert len(granted) == 5
    await db_session.refresh(user)
    assert user.balance == 550  # 500 + 5*10


async def test_sync_no_op_when_no_tiers_configured(db_session):
    user = await _make_user(db_session, 990004)
    granted = await league_service.sync_league_rewards_for_user(db_session, user)
    assert granted == []


async def test_sync_grants_pack_reward(db_session):
    pack = await create_pack(db_session, "league-test-pack", price=0, card_count=1, probabilities={Rarity.common: 1.0})
    await create_player(db_session)
    tier = LeagueTier(name="Дворовая лига", min_rating=0, reward_coins=0, reward_pack_id=pack.id, sort_order=0)
    db_session.add(tier)
    await db_session.commit()

    user = await _make_user(db_session, 990005)
    granted = await league_service.sync_league_rewards_for_user(db_session, user)
    await db_session.commit()

    assert len(granted) == 1
    cards = (await db_session.execute(select(UserCard).where(UserCard.owner_id == user.id))).scalars().all()
    assert len(cards) == 1
    assert cards[0].source == CardSource.league_reward


async def test_get_league_status_reports_current_and_next(db_session):
    tier0 = LeagueTier(name="Дворовая лига", min_rating=0, sort_order=0)
    tier1 = LeagueTier(name="Городская лига", min_rating=100, sort_order=1)
    db_session.add_all([tier0, tier1])
    await db_session.commit()

    user = await _make_user(db_session, 990006)
    user.tactics_rating = 40
    db_session.add(user)
    await db_session.commit()

    status = await league_service.get_league_status(db_session, user)
    assert status.total_rating == 40
    assert status.current_league.id == tier0.id
    assert status.next_league.id == tier1.id
    assert status.points_to_next == 60


async def test_get_league_status_null_current_when_no_tiers(db_session):
    user = await _make_user(db_session, 990007)
    status = await league_service.get_league_status(db_session, user)
    assert status.current_league is None
    assert status.next_league is None
    assert status.points_to_next is None


async def test_arena_match_triggers_league_reward_via_api(client, db_session, bot_token):
    """Uses the same lineup-setup + play-to-completion pattern as
    test_lineups_matches.py's test_full_match_loop_finishes_and_credits_once
    (see _build_full_squad/_play_to_completion there). A min_rating=0 tier
    is claimed on the very first call regardless of win/loss/draw — even a
    loss only clamps arena_rating back down to 0, which still satisfies
    min_rating <= 0 — so this test doesn't need to control the match's
    random outcome to be deterministic."""
    from app.services.lineup_service import FORMATION_SLOTS

    tier = LeagueTier(name="Дворовая лига", min_rating=0, reward_coins=25, sort_order=0)
    db_session.add(tier)
    await db_session.commit()

    headers = telegram_headers(990010, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 990010)

    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    match = resp.json()
    guard = 0
    action_by_kind = {"attack": "shoot", "defense": "tackle", "breakaway": "strike"}
    while match["status"] == "in_progress":
        guard += 1
        assert guard < 30
        action = action_by_kind[match["pending_moment"]["kind"]]
        resp = await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": action})
        assert resp.status_code == 200
        match = resp.json()

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert any(n["type"] == "league_promoted" for n in notifications)


async def test_get_leagues_endpoint_lists_tiers_in_order(client, db_session, bot_token):
    tier_hi = LeagueTier(name="Высшая лига", min_rating=500, sort_order=1)
    tier_lo = LeagueTier(name="Дворовая лига", min_rating=0, sort_order=0)
    db_session.add_all([tier_hi, tier_lo])
    await db_session.commit()

    headers = telegram_headers(990020, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/leagues", headers=headers)
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()]
    assert names == ["Дворовая лига", "Высшая лига"]


async def test_get_league_status_endpoint(client, db_session, bot_token):
    tier = LeagueTier(name="Дворовая лига", min_rating=0, sort_order=0)
    db_session.add(tier)
    await db_session.commit()

    headers = telegram_headers(990021, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)

    resp = await client.get("/api/v1/leagues/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_rating"] == 0
    assert body["current_league"]["name"] == "Дворовая лига"


async def test_league_rating_ranking_metric(client, db_session, bot_token):
    headers_a = telegram_headers(990022, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    user_a = await get_user_by_telegram_id(db_session, 990022)
    user_a.arena_rating = 10
    user_a.tactics_rating = 5
    db_session.add(user_a)
    await db_session.commit()

    resp = await client.get("/api/v1/leaderboard/ranking?metric=league_rating", headers=headers_a)
    assert resp.status_code == 200
    body = resp.json()
    assert body["me"]["value"] == 15
