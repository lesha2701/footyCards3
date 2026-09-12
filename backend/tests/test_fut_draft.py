from types import SimpleNamespace

import pytest_asyncio
from sqlalchemy.orm.attributes import flag_modified

from app.models.enums import Position, Rarity
from app.services import fut_draft_service
from app.services.fut_draft_service import MIN_STRONG_OR_BETTER_SLOTS, STRONG_OR_BETTER_TIERS
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


def test_lazy_tier_guarantees_hold_across_many_full_runs():
    """Simulates the whole 11-slot lazy-roll process (as open_slot would,
    slot-by-slot, in an arbitrary open order) and checks the same whole-draft
    guarantees the old precomputed-sequence design had."""
    for _ in range(200):
        state = {"weak_streak": 0, "jackpot_seen": False, "strong_or_better_count": 0}
        tiers = []
        remaining = 11
        while remaining > 0:
            tier = fut_draft_service._roll_tier_for_open_slot(_FAKE_CONFIG, state, remaining)
            tiers.append(tier)
            state["weak_streak"] = state["weak_streak"] + 1 if tier == "weak" else 0
            if tier == "jackpot":
                state["jackpot_seen"] = True
            if tier in STRONG_OR_BETTER_TIERS:
                state["strong_or_better_count"] += 1
            remaining -= 1

        assert len(tiers) == 11
        assert "jackpot" in tiers
        assert sum(1 for t in tiers if t in STRONG_OR_BETTER_TIERS) >= MIN_STRONG_OR_BETTER_SLOTS
        max_weak_streak = 0
        current = 0
        for tier in tiers:
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


async def _choose_formation(client, headers, session_id, formation_options):
    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/formation", headers=headers, json={"formation": formation_options[0]},
    )
    assert resp.status_code == 200
    return resp.json()


async def _seed_active_round(db_session, session_id, active_round):
    """Bypasses /match/start (which now always opens a Card Arena round) to
    put a session directly into a Тактико/Пенальти round, so those still-
    present-but-currently-unreachable-by-the-roulette code paths stay
    covered by their own tests."""
    from app.models.game import GameSession

    session = await db_session.get(GameSession, session_id)
    state = dict(session.server_state)
    state["active_round"] = active_round
    session.server_state = state
    flag_modified(session, "server_state")
    db_session.add(session)
    await db_session.commit()


async def _draft_full_squad(client, headers, session_id, formation_options):
    state = await _choose_formation(client, headers, session_id, formation_options)
    empty_slots = [s["slot_code"] for s in state["slots"] if s["player"] is None]
    for slot_code in empty_slots:
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": slot_code},
        )
        assert resp.status_code == 200
        state = resp.json()
        candidate_id = state["candidates"][0]["id"]
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": candidate_id},
        )
        assert resp.status_code == 200
        state = resp.json()
    return state


async def test_fut_draft_public_config_exposes_entry_cost(client, db_session, bot_token):
    from app.services.game_config_service import get_config

    headers = await _register(client, bot_token, 771000)
    config = await get_config(db_session)

    resp = await client.get("/api/v1/games/fut-draft/config", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["entry_cost"] == config.fut_draft_entry_cost


async def test_fut_draft_start_charges_entry_cost(client, db_session, bot_token):
    from app.services.game_config_service import get_config

    _headers, body = await _start(client, db_session, bot_token, 770001)
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


async def test_fut_draft_can_open_slots_in_any_order(client, db_session, bot_token):
    """The FIFA-style point: the player chooses which position to fill next,
    not a fixed sequential order."""
    headers, body = await _start(client, db_session, bot_token, 770003)
    session_id = body["session_id"]
    state = await _choose_formation(client, headers, session_id, body["formation_options"])
    slot_codes = [s["slot_code"] for s in state["slots"]]

    # Open the LAST slot in the formation's own list first.
    last_slot = slot_codes[-1]
    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": last_slot})
    assert resp.status_code == 200
    opened = resp.json()
    assert opened["pending_slot"] == last_slot
    assert len(opened["candidates"]) == 3

    # Cannot open a second slot while one is still pending.
    other_slot = slot_codes[0]
    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": other_slot})
    assert resp.status_code == 409

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": opened["candidates"][0]["id"]},
    )
    assert resp.status_code == 200
    state = resp.json()
    filled = next(s for s in state["slots"] if s["slot_code"] == last_slot)
    assert filled["player"] is not None
    assert state["pending_slot"] is None


async def test_fut_draft_full_draft_reaches_ready_phase_with_eleven_picks(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770004)
    state = await _draft_full_squad(client, headers, body["session_id"], body["formation_options"])

    assert state["phase"] == "ready"
    assert all(s["player"] is not None for s in state["slots"])
    assert state["team_strength"] > 0
    picked_ids = [s["player"]["id"] for s in state["slots"]]
    assert len(picked_ids) == len(set(picked_ids))


async def test_fut_draft_team_strength_grows_live_during_drafting(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770005)
    session_id = body["session_id"]
    state = await _choose_formation(client, headers, session_id, body["formation_options"])
    assert state["team_strength"] == 0

    slot_code = state["slots"][0]["slot_code"]
    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": slot_code})
    candidates = resp.json()["candidates"]

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": candidates[0]["id"]},
    )
    state = resp.json()
    assert state["team_strength"] > 0
    assert state["last_pick_strength_delta"] == state["team_strength"]


async def test_fut_draft_rejects_picking_a_card_not_offered(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770006)
    session_id = body["session_id"]
    state = await _choose_formation(client, headers, session_id, body["formation_options"])
    slot_code = state["slots"][0]["slot_code"]

    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": slot_code})
    offered_ids = {c["id"] for c in resp.json()["candidates"]}

    from app.models.player import Player
    from sqlalchemy import select
    result = await db_session.execute(select(Player).where(Player.id.notin_(offered_ids)).limit(1))
    other_player = result.scalar_one()

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": other_player.id},
    )
    assert resp.status_code == 409


def _force_one_goal_breakaway(monkeypatch):
    """Card Arena rounds now run the exact real match_service engine against
    the draft squad — forcing a deterministic outcome means controlling that
    engine's own inputs, not a FUT-Draft-only shortcut. A single user
    breakaway (empty net) moment is interactive (team == "user") but skips
    all of match_situations' actor/situation machinery, and pinning
    random() so `_resolve_breakaway`'s miss roll never fires guarantees the
    "strike" action always scores."""
    fixed_moment = {
        "minute": 10, "kind": "shot", "team": "user", "shot_type": "empty_net",
        "situation_kind": "breakaway_user", "situation_id": None, "actors": {},
        "description": "Пустые ворота! Не отправь мяч в трибуны.", "actions": ["strike"],
    }
    monkeypatch.setattr(fut_draft_service, "_generate_moment_queue", lambda *a, **k: [dict(fixed_moment)])
    monkeypatch.setattr(fut_draft_service.random, "random", lambda: 0.99)


async def test_fut_draft_wins_all_four_matches_and_claims_top_reward(client, db_session, bot_token, monkeypatch):
    from app.services.game_config_service import get_config

    _force_one_goal_breakaway(monkeypatch)

    headers, body = await _start(client, db_session, bot_token, 770007)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])

    last_result = None
    for _ in range(4):
        resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
        assert resp.status_code == 200
        opened = resp.json()
        assert opened["game_type"] == "card_arena"
        assert opened["round_in_progress"] is True
        assert opened["pending_moment"]["actions"] == ["strike"]

        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/card-arena/action", headers=headers, json={"action": "strike"},
        )
        assert resp.status_code == 200
        last_result = resp.json()
        assert last_result["round_in_progress"] is False
        assert len(last_result["events"]) >= 1

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

    user = await get_user_by_telegram_id(db_session, 770007)
    assert user.fut_draft_best_squad_strength == claim_body["team_strength"]

    second_claim = await client.post(f"/api/v1/games/fut-draft/{session_id}/claim", headers=headers)
    assert second_claim.status_code == 409


async def test_fut_draft_card_arena_round_plays_out_with_the_real_engine(client, db_session, bot_token):
    """No monkeypatching here — a real Card Arena round against the drafted
    squad, driven by /card-arena/action the same way the frontend's "skip"
    auto-play does (pick whichever action is offered), just to prove the
    reused match_service engine actually runs end-to-end against a temporary
    draft squad without exceptions and produces a coherent result."""
    headers, body = await _start(client, db_session, bot_token, 770013)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])

    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
    assert resp.status_code == 200
    round_state = resp.json()
    assert round_state["game_type"] == "card_arena"

    for _ in range(200):  # generous upper bound; a real round is a few dozen moments at most
        if not round_state["round_in_progress"]:
            break
        pending = round_state["pending_moment"]
        assert pending is not None
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/card-arena/action",
            headers=headers, json={"action": pending["actions"][0]},
        )
        assert resp.status_code == 200
        round_state = resp.json()

    assert round_state["round_in_progress"] is False
    assert round_state["result"] in ("win", "draw", "loss")
    assert len(round_state["events"]) > 0
    assert round_state["wins"] == (1 if round_state["result"] == "win" else 0)


async def test_fut_draft_tactico_round_is_interactive_and_stops_the_series_on_loss(client, db_session, bot_token, monkeypatch):
    """Тактико's turn-based implementation stays in the codebase (in case
    round-type variety comes back) even though every round is Card Arena
    for now — seed a round directly into a Тактико state (bypassing
    /match/start, which can no longer open one) to keep it covered."""
    from app.services.game_config_service import get_config

    # random() >= any win_prob in (0,1) forces every phase to fail for the
    # user; the second random() call (bot's punish roll) also never fires
    # since 1.0 is never < the (<1) threshold, so it's a clean 0-0 fizzle...
    # to get an actual bot goal instead, alternate: first call fails the user,
    # second call (bot's roll) always succeeds.
    calls = iter([0.99, 0.0] * 10)
    monkeypatch.setattr(fut_draft_service.random, "random", lambda: next(calls))

    headers, body = await _start(client, db_session, bot_token, 770008)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])
    await _seed_active_round(db_session, session_id, {
        "game_type": "tactico", "bot_strength": 500, "phase": 0, "user_score": 0, "bot_score": 0,
    })

    result = None
    for _ in range(4):
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/tactico/phase", headers=headers,
            json={"choice": fut_draft_service.TACTIC_CHOICES[0]},
        )
        assert resp.status_code == 200
        result = resp.json()

    assert result["round_in_progress"] is False
    assert result["result"] == "loss"
    assert result["bot_score"] > result["user_score"]
    assert result["wins"] == 0
    assert result["is_finished"] is True
    assert result["status"] == "lost"

    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/match/start", headers=headers)
    assert resp.status_code == 409

    config = await get_config(db_session)
    claim = await client.post(f"/api/v1/games/fut-draft/{session_id}/claim", headers=headers)
    assert claim.status_code == 200
    assert claim.json()["reward_coins"] == config.fut_draft_reward_win_0


async def test_fut_draft_tactico_rejects_an_unknown_choice(client, db_session, bot_token, monkeypatch):
    headers, body = await _start(client, db_session, bot_token, 770012)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])
    await _seed_active_round(db_session, session_id, {
        "game_type": "tactico", "bot_strength": 500, "phase": 0, "user_score": 0, "bot_score": 0,
    })

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/tactico/phase", headers=headers, json={"choice": "Несуществующий вариант"},
    )
    assert resp.status_code == 409


async def test_fut_draft_penalty_round_is_interactive_and_uses_a_squad_card(client, db_session, bot_token, monkeypatch):
    """Пенальти's kick-by-kick implementation also stays in the codebase for
    the same reason as Тактико's above — seeded directly the same way."""
    # player_miss_chance -> 0 for the user's kicks, a fixed positive value
    # for the bot's — _resolve_shot keys off that alone here, sidestepping
    # the shot/dive zone randomness so the outcome is fully deterministic.
    monkeypatch.setattr(fut_draft_service, "player_miss_chance", lambda rating: 0.0)
    monkeypatch.setattr(fut_draft_service, "_resolve_shot", lambda miss_chance, shot_zone, dive_zone: "miss" if miss_chance > 0 else "goal")

    headers, body = await _start(client, db_session, bot_token, 770010)
    session_id = body["session_id"]
    await _draft_full_squad(client, headers, session_id, body["formation_options"])
    await _seed_active_round(db_session, session_id, {
        "game_type": "penalty", "miss_chance": 0.0, "bot_miss_chance": 0.5,
        "kick_number": 0, "user_score": 0, "bot_score": 0,
    })

    result = None
    for _ in range(5):
        resp = await client.post(
            f"/api/v1/games/fut-draft/{session_id}/penalty/kick", headers=headers, json={"direction": "top_left"},
        )
        assert resp.status_code == 200
        result = resp.json()

    assert result["round_in_progress"] is False
    assert result["game_type"] == "penalty"
    assert result["result"] == "win"
    assert result["user_score"] == 5
    assert result["bot_score"] == 0
    assert result["is_finished"] is False  # only 1 of 4 draft matches played
    assert result["wins"] == 1


async def test_fut_draft_chemistry_hints_reflect_club_and_country_bonuses(client, db_session, bot_token):
    headers, body = await _start(client, db_session, bot_token, 770011)
    session_id = body["session_id"]
    state = await _choose_formation(client, headers, session_id, body["formation_options"])
    slot_code = state["slots"][0]["slot_code"]

    resp = await client.post(f"/api/v1/games/fut-draft/{session_id}/slot", headers=headers, json={"slot_code": slot_code})
    candidate = resp.json()["candidates"][0]

    resp = await client.post(
        f"/api/v1/games/fut-draft/{session_id}/pick", headers=headers, json={"player_id": candidate["id"]},
    )
    state = resp.json()
    assert any(hint.startswith("На своей позиции") for hint in state["chemistry_hints"])


async def test_fut_draft_leaderboard_orders_by_best_squad_strength(client, db_session, bot_token, monkeypatch):
    # A single opponent breakaway (empty net) is auto-resolved inside
    # /match/start itself (non-interactive — see _is_interactive), so one
    # call is enough to finalize the round as a loss, no follow-up action
    # needed.
    fixed_moment = {
        "minute": 10, "kind": "shot", "team": "opponent", "shot_type": "empty_net",
        "situation_kind": "breakaway_opponent", "situation_id": None, "actors": {}, "description": "", "actions": [],
    }
    monkeypatch.setattr(fut_draft_service, "_generate_moment_queue", lambda *a, **k: [dict(fixed_moment)])
    monkeypatch.setattr(fut_draft_service.random, "random", lambda: 0.99)

    headers_a, body_a = await _start(client, db_session, bot_token, 770009)
    await _draft_full_squad(client, headers_a, body_a["session_id"], body_a["formation_options"])
    await client.post(f"/api/v1/games/fut-draft/{body_a['session_id']}/match/start", headers=headers_a)
    await client.post(f"/api/v1/games/fut-draft/{body_a['session_id']}/claim", headers=headers_a)

    user_a = await get_user_by_telegram_id(db_session, 770009)

    resp = await client.get("/api/v1/games/fut-draft/leaderboard", headers=headers_a)
    assert resp.status_code == 200
    entries = resp.json()
    assert any(e["user_id"] == user_a.id for e in entries)
    strengths = [e["best_squad_strength"] for e in entries]
    assert strengths == sorted(strengths, reverse=True)
