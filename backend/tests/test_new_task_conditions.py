import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, MatchDifficulty, TaskCategory, TaskConditionType
from app.models.game import GameSession
from app.models.game_config import GameConfig
from app.models.match import Match
from app.models.task import TaskDefinition
from app.services import match_service, penalty_service
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id)


async def _get_config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
        config = await db_session.get(GameConfig, 1)
    return config


async def _build_full_squad(db_session, user_id: int, *, countries: list[str] | None = None) -> list[dict]:
    slots = []
    for i, slot in enumerate(FORMATION_SLOTS):
        country = countries[i] if countries else "Тестландия"
        player = await create_player(db_session, rating=80, position=slot.ideal_position, country=country)
        card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    return slots


async def _fetch_task(client, headers, code: str) -> dict:
    tasks = (await client.get("/api/v1/tasks", headers=headers)).json()["regular"]
    return next(t for t in tasks if t["code"] == code)


# ---------------------------------------------------------------------------
# match_same_country
# ---------------------------------------------------------------------------

async def test_same_country_task_completes_with_uniform_lineup(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="same_country", name="Same country", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.match_same_country, target_value=1, reward_coins=50,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840001, bot_token)
    headers = telegram_headers(840001, bot_token)

    task_before = await _fetch_task(client, headers, "same_country")
    assert task_before["is_completed"] is False

    slots = await _build_full_squad(db_session, user.id)  # all default to the same country
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200

    task_after = await _fetch_task(client, headers, "same_country")
    assert task_after["is_completed"] is True


async def test_same_country_task_not_completed_with_mixed_lineup(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="same_country", name="Same country", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.match_same_country, target_value=1, reward_coins=50,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840002, bot_token)
    headers = telegram_headers(840002, bot_token)

    countries = ["Тестландия"] * (len(FORMATION_SLOTS) - 1) + ["Другая страна"]
    slots = await _build_full_squad(db_session, user.id, countries=countries)
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200

    task_after = await _fetch_task(client, headers, "same_country")
    assert task_after["is_completed"] is False


# ---------------------------------------------------------------------------
# arena_clean_sheet_wins (metric_counter)
# ---------------------------------------------------------------------------

async def test_arena_clean_sheet_win_progresses_task(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="clean_sheets", name="Clean sheets", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="arena_clean_sheet_wins", target_value=2,
            reward_coins=50,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840003, bot_token)
    headers = telegram_headers(840003, bot_token)
    await _fetch_task(client, headers, "clean_sheets")  # assigns the slot

    config = await _get_config(db_session)

    def _make_match(user_score: int, opponent_score: int) -> Match:
        match = Match(
            user_id=user.id, opponent_name="Bot", difficulty=MatchDifficulty.medium,
            user_team_strength=80, opponent_team_strength=80,
            user_score=user_score, opponent_score=opponent_score,
        )
        db_session.add(match)
        return match

    # A win that concedes a goal doesn't count as a clean sheet.
    match1 = _make_match(2, 1)
    await db_session.flush()
    await match_service._finalize_match(db_session, user, match1, {"user_score": 2, "opponent_score": 1}, config)

    task_mid = await _fetch_task(client, headers, "clean_sheets")
    assert task_mid["is_completed"] is False
    assert task_mid["progress"] == 0

    # Two clean-sheet wins should reach the target.
    for _ in range(2):
        match = _make_match(3, 0)
        await db_session.flush()
        await match_service._finalize_match(db_session, user, match, {"user_score": 3, "opponent_score": 0}, config)

    task_after = await _fetch_task(client, headers, "clean_sheets")
    assert task_after["is_completed"] is True
    assert task_after["progress"] == 2


# ---------------------------------------------------------------------------
# penalty_win_max_rating
# ---------------------------------------------------------------------------

async def _play_penalty_to_forced_win(client, headers, session_id: str, monkeypatch) -> None:
    # Player never misses, and the "bot's shot direction"/"keeper's guess"
    # roll (shared `random.choice` call site) never matches the player's own
    # direction, so the player also always beats the keeper on offense;
    # forcing the bot to always miss on defense guarantees a clean win
    # instead of leaving the outcome to chance.
    monkeypatch.setattr(penalty_service, "player_miss_chance", lambda rating: 0.0)
    monkeypatch.setattr(penalty_service.random, "choice", lambda seq: "right")
    for _ in range(10):
        resp = await client.post(f"/api/v1/games/penalty/{session_id}/kick", headers=headers, json={"direction": "left"})
        assert resp.status_code == 200
        if resp.json()["is_finished"]:
            assert resp.json()["result"] == "win"
            return
    raise AssertionError("Penalty shootout did not finish within regulation kicks")


async def test_penalty_win_with_low_rated_player_completes_task(client, db_session, bot_token, monkeypatch):
    db_session.add(
        TaskDefinition(
            code="penalty_underdog", name="Underdog win", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.penalty_win_max_rating, condition_params={"max_rating": 70},
            target_value=1, reward_coins=50,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840004, bot_token)
    headers = telegram_headers(840004, bot_token)
    await _fetch_task(client, headers, "penalty_underdog")

    config = await _get_config(db_session)
    config.penalty_bot_miss_chance = 1.0
    db_session.add(config)
    await db_session.commit()

    player = await create_player(db_session, rating=65)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    await _play_penalty_to_forced_win(client, headers, session_id, monkeypatch)

    task_after = await _fetch_task(client, headers, "penalty_underdog")
    assert task_after["is_completed"] is True


async def test_penalty_win_with_high_rated_player_does_not_complete_task(client, db_session, bot_token, monkeypatch):
    db_session.add(
        TaskDefinition(
            code="penalty_underdog", name="Underdog win", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.penalty_win_max_rating, condition_params={"max_rating": 70},
            target_value=1, reward_coins=50,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840005, bot_token)
    headers = telegram_headers(840005, bot_token)
    await _fetch_task(client, headers, "penalty_underdog")

    config = await _get_config(db_session)
    config.penalty_bot_miss_chance = 1.0
    db_session.add(config)
    await db_session.commit()

    player = await create_player(db_session, rating=90)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    start = await client.post("/api/v1/games/penalty/start", headers=headers, json={"user_card_id": card.id})
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    await _play_penalty_to_forced_win(client, headers, session_id, monkeypatch)

    task_after = await _fetch_task(client, headers, "penalty_underdog")
    assert task_after["is_completed"] is False


# ---------------------------------------------------------------------------
# memory_levels_completed (metric_counter)
# ---------------------------------------------------------------------------

async def test_memory_levels_completed_progresses_task(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="memory_levels", name="Memory levels", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="memory_levels_completed", target_value=2,
            reward_coins=50,
        )
    )
    await db_session.commit()

    await _register(client, db_session, 840006, bot_token)
    headers = telegram_headers(840006, bot_token)
    await _fetch_task(client, headers, "memory_levels")

    start = (await client.post("/api/v1/games/memory/start", headers=headers)).json()
    session_id = start["session_id"]

    resp = await client.post(
        f"/api/v1/games/memory/{session_id}/submit", headers=headers, json={"answer": start["sequence"]}
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is True

    task_mid = await _fetch_task(client, headers, "memory_levels")
    assert task_mid["progress"] == 1
    assert task_mid["is_completed"] is False

    next_sequence = resp.json()["next_round"]["sequence"]
    resp = await client.post(
        f"/api/v1/games/memory/{session_id}/submit", headers=headers, json={"answer": next_sequence}
    )
    assert resp.status_code == 200
    assert resp.json()["correct"] is True

    task_after = await _fetch_task(client, headers, "memory_levels")
    assert task_after["progress"] == 2
    assert task_after["is_completed"] is True


# ---------------------------------------------------------------------------
# saboteur_levels_cleared (metric_counter)
# ---------------------------------------------------------------------------

async def test_saboteur_levels_cleared_progresses_task(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="saboteur_levels", name="Saboteur levels", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="saboteur_levels_cleared", target_value=1,
            reward_coins=50,
        )
    )
    await db_session.commit()

    await _register(client, db_session, 840007, bot_token)
    headers = telegram_headers(840007, bot_token)
    await _fetch_task(client, headers, "saboteur_levels")

    start = (await client.post("/api/v1/games/saboteur/start", headers=headers)).json()
    session_id = start["session_id"]

    db_session.expire_all()
    session = await db_session.get(GameSession, session_id)
    line_stewards = session.server_state["line_stewards"]
    safe_index = next(i for i in range(5) if i not in line_stewards)

    resp = await client.post(
        f"/api/v1/games/saboteur/{session_id}/reveal", headers=headers, json={"cell_index": safe_index}
    )
    assert resp.status_code == 200
    assert resp.json()["is_steward"] is False

    task_after = await _fetch_task(client, headers, "saboteur_levels")
    assert task_after["is_completed"] is True
    assert task_after["progress"] == 1


# ---------------------------------------------------------------------------
# Repeatable task pool: a claimed task goes back into rotation and its
# progress is tracked relative to when it was (re-)assigned, not the
# player's lifetime total.
# ---------------------------------------------------------------------------

async def test_metric_counter_task_resets_progress_when_reassigned(client, db_session, bot_token):
    from app.models.enums import Rarity
    from tests.factories import create_pack

    db_session.add(
        TaskDefinition(
            code="pack_opener_repeat", name="Pack opener", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=1, reward_coins=10,
        )
    )
    await db_session.commit()

    await _register(client, db_session, 840008, bot_token)
    headers = telegram_headers(840008, bot_token)
    await _fetch_task(client, headers, "pack_opener_repeat")

    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "repeat-pack-1", price=0, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 200

    task_done = await _fetch_task(client, headers, "pack_opener_repeat")
    assert task_done["is_completed"] is True
    assert task_done["progress"] == 1

    claim = await client.post(f"/api/v1/tasks/{task_done['user_task_id']}/claim", headers=headers)
    assert claim.status_code == 200

    # It's the only definition in the pool, so a plain refetch (no longer
    # excluded, since that exclusion only applied to the claim's own refill)
    # deterministically brings it right back — reset, not still "done".
    task_reassigned = await _fetch_task(client, headers, "pack_opener_repeat")
    assert task_reassigned["is_completed"] is False
    assert task_reassigned["progress"] == 0

    # Lifetime packs_opened is already 1 at this point — if progress were
    # compared to the lifetime total instead of a fresh baseline, this
    # reassigned instance would already read as complete with no further
    # action. It must actually require a second pack.
    pack2 = await create_pack(db_session, "repeat-pack-2", price=0, card_count=1, probabilities={Rarity.common: 1.0})
    resp = await client.post(f"/api/v1/packs/{pack2.id}/open", headers=headers, json={})
    assert resp.status_code == 200

    task_after_second = await _fetch_task(client, headers, "pack_opener_repeat")
    assert task_after_second["is_completed"] is True
    assert task_after_second["progress"] == 1


async def test_match_min_rating_task_is_repeatable_after_claim(client, db_session, bot_token):
    db_session.add(
        TaskDefinition(
            code="repeat_squad_check", name="Squad check", description="test", category=TaskCategory.regular,
            condition_type=TaskConditionType.match_min_rating, condition_params={"min_rating": 67},
            target_value=1, reward_coins=10,
        )
    )
    await db_session.commit()

    user = await _register(client, db_session, 840009, bot_token)
    headers = telegram_headers(840009, bot_token)
    await _fetch_task(client, headers, "repeat_squad_check")

    slots = await _build_full_squad(db_session, user.id)
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200

    task_done = await _fetch_task(client, headers, "repeat_squad_check")
    assert task_done["is_completed"] is True

    claim = await client.post(f"/api/v1/tasks/{task_done['user_task_id']}/claim", headers=headers)
    assert claim.status_code == 200

    task_reassigned = await _fetch_task(client, headers, "repeat_squad_check")
    assert task_reassigned["is_completed"] is False

    resp = await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200

    task_done_again = await _fetch_task(client, headers, "repeat_squad_check")
    assert task_done_again["is_completed"] is True
