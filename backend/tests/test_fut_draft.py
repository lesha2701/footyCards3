from types import SimpleNamespace

import pytest_asyncio

from app.models.enums import Position, Rarity
from app.services import fut_draft_service
from app.services.fut_draft_service import MIN_STRONG_OR_BETTER_SLOTS, STRONG_OR_BETTER_TIERS, _generate_tier_sequence
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

_FAKE_CONFIG = SimpleNamespace(
    fut_draft_weak_chance=20, fut_draft_normal_chance=40, fut_draft_strong_chance=25,
    fut_draft_top_chance=12, fut_draft_jackpot_chance=3,
)


@pytest_asyncio.fixture(autouse=True)
async def _seed_full_pool(db_session):
    for position in Position:
        for rarity in (Rarity.common, Rarity.rare, Rarity.epic, Rarity.legendary):
            for _ in range(3):
                await create_player(db_session, rarity=rarity, position=position)


def test_tier_sequence_guarantees_hold_across_many_runs():
    for _ in range(200):
        sequence = _generate_tier_sequence(_FAKE_CONFIG, 11)
        assert len(sequence) == 11
        assert "jackpot" in sequence
        assert sum(1 for t in sequence if t in STRONG_OR_BETTER_TIERS) >= MIN_STRONG_OR_BETTER_SLOTS
        max_weak_streak = 0
        current = 0
        for tier in sequence:
            current = current + 1 if tier == "weak" else 0
            max_weak_streak = max(max_weak_streak, current)
        assert max_weak_streak <= 2


async def _register(client, bot_token, telegram_id):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    return headers


async def _start(client, db_session, bot_token, telegram_id):
    headers = await _register(client, bot_token, telegram_id)
    resp = await client.post("/api/v1/games/fut-draft/start", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    return headers, body


async def _draft_full_squad(client, headers, session_id, formation_options):
    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/formation", headers=headers, json={"formation": formation_options[0]},
    )
    assert resp.status_code == 200
    state = resp.json()
    while state["phase"] == "drafting":
        candidate_id = state["candidates"][0]["id"]
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": candidate_id},
        )
        assert resp.status_code == 200
        state = resp.json()
    return state


async def test_fut_draft_start_charges_entry_cost(client, db_session, bot_token):
    from app.services.game_config_service import get_config

    headers, body = await _start(client, db_session, bot_token, 770001)
    config = await get_config(db_session)

    assert len(body["formation_options"]) == 3
    assert body["entry_cost"] == config.fut_draft_entry_cost

    user = await get_user_by_telegram_id(db_session, 770001)
    assert user.balance == body["new_balance"]


async def test_fut_draft_choose_formation_rejects_unoffered_formation(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770002)
    all_formations = {"4-3-3", "4-4-2", "3-5-2", "5-3-2"}
    not_offered = next(f for f in all_formations if f not in body["formation_options"])

    resp = await client.post(
        f"/api/v1/games/fut-draft/{body['session_id']}/formation", headers=headers, json={"formation": not_offered},
    )
    assert resp.status_code == 409


async def test_fut_draft_full_draft_reaches_ready_phase_with_eleven_picks(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770003)
    state = await _draft_full_squad(client, headers, body["session_id"], body["formation_options"])

    assert state["phase"] == "ready"
    assert len(state["picks"]) == 11
    assert state["team_strength"] > 0
    # No duplicate players across the assembled squad.
    picked_ids = [p["player"]["id"] for p in state["picks"]]
    assert len(picked_ids) == len(set(picked_ids))


async def test_fut_draft_rejects_picking_a_card_not_offered(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770004)
    session_id = body["session_id"]

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/formation", headers=headers, json={"formation": body["formation_options"][0]},
    )
    state = resp.json()
    offered_ids = {c["id"] for c in state["candidates"]}

    from app.models.player import Player
    from sqlalchemy import select
    result = await db_session.execute(select(Player).where(Player.id.notin_(offered_ids)).limit(1))
    other_player = result.scalar_one()

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": other_player.id},
    )
    assert resp.status_code == 409


async def test_fut_draft_wins_all_four_matches_and_claims_top_reward(client, db_session, bot_token, monkeypatch):
    from app.services.game_config_service import get_config

    monkeypatch.setattr(fut_draft_service, "_resolve_match", lambda user_strength, bot_strength: ("win", 3, 0))

    headers, body = await _start(client, db_session, bot_token, 770005)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])

    last_result = None
    for _ in range(4):
        resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
        assert resp.status_code == 200
        last_result = resp.json()

    assert last_result["wins"] == 4
    assert last_result["is_finished"] is True
    assert last_result["status"] == "won"

    config = await get_config(db_session)
    claim = await client.post(f"/api/v1/games/fut-draft/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    claim_body = claim.json()
    assert claim_body["reward_coins"] == config.fut_draft_reward_win_4
    assert claim_body["wins"] == 4
    assert claim_body["is_new_best"] is True

    user = await get_user_by_telegram_id(db_session, 770005)
    assert user.fut_draft_best_squad_strength == claim_body["team_strength"]

    second_claim = await client.post(f"/api/v1/games/fut-draft/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_fut_draft_loses_first_match_and_stops_the_series(client, db_session, bot_token, monkeypatch):
    from app.services.game_config_service import get_config

    monkeypatch.setattr(fut_draft_service, "_resolve_match", lambda user_strength, bot_strength: ("loss", 0, 2))

    headers, body = await _start(client, db_session, bot_token, 770006)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])

    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
    assert resp.status_code == 200
    result = resp.json()
    assert result["wins"] == 0
    assert result["is_finished"] is True
    assert result["status"] == "lost"

    # The series is over — a further match/start attempt is rejected.
    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
    assert resp.status_code == 409

    config = await get_config(db_session)
    claim = await client.post(f"/api/v1/games/fut-draft/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == config.fut_draft_reward_win_0


async def test_fut_draft_leaderboard_orders_by_best_squad_strength(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(fut_draft_service, "_resolve_match", lambda user_strength, bot_strength: ("loss", 0, 1))

    headers_a, body_a = await _start(client, db_session, bot_token, 770007)
    await _draft_full_squad(client, headers_a, body_a["session_id"], body_a["formation_options"])
    await client.post(f"/api/v1/games/fut-draft/{body_a['session_id']}/match/start", headers=headers_a)
    await client.post(f"/api/v1/games/fut-draft/{body_a['session_id']}/claim", headers=headers_a)

    user_a = await get_user_by_telegram_id(db_session, 770007)

    resp = await client.get("/api/v1/games/fut-draft/leaderboard", headers=headers_a)
    assert resp.status_code == 200
    entries = resp.json()
    assert any(e["user_id"] == user_a.id for e in entries)
    strengths = [e["best_squad_strength"] for e in entries]
    assert strengths == sorted(strengths, reverse=True)
