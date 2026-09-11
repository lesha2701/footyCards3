from app.services import tournament_match_engine as engine


class _FakeConfig:
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


# _FakeMatchConfig exposes every match_* field the resolution code reads,
# mirroring GameConfig's defaults (see app/models/game_config.py) —
# _FakeConfig above only covers the shot-type weights
# club_tactical_matchup_service._pick_shot_type needs, so this subclass adds
# the rest rather than duplicating them.
class _FakeMatchConfig(_FakeConfig):
    match_shot_miss_chance_min = 0.08
    match_shot_miss_chance_max = 0.30
    match_defender_block_chance_min = 0.10
    match_defender_block_chance_max = 0.35
    match_attack_shoot_miss_chance_min = 0.08
    match_attack_shoot_miss_chance_max = 0.32
    match_pass_fail_chance_min = 0.05
    match_pass_fail_chance_max = 0.28
    match_receiver_shot_miss_chance_min = 0.05
    match_receiver_shot_miss_chance_max = 0.22
    match_tackle_foul_chance_min = 0.06
    match_tackle_foul_chance_max = 0.30
    match_tackle_red_chance_min = 0.05
    match_tackle_red_chance_max = 0.22
    match_block_fail_chance_min = 0.10
    match_block_fail_chance_max = 0.32
    match_keeper_save_chance_min = 0.35
    match_keeper_save_chance_max = 0.75
    match_red_card_strength_penalty_pct = 0.12
    match_penalty_gk_rating_penalty = 6
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    club_tactical_tackle_attempt_chance = 0.20
    club_tactical_injury_chance = 0.35


def _hand_built_moment(shot_type: str = "in_box") -> dict:
    return {
        "minute": 10,
        "shot_type": shot_type,
        "is_box": shot_type == "in_box",
        "actors": {
            "shooter": {"club_card_id": 1, "player_id": 1, "name": "Shooter", "rating": 75, "position": "ST"},
            "pass_target": {"club_card_id": 2, "player_id": 2, "name": "PassTarget", "rating": 75, "position": "CAM"},
            "defender": {"club_card_id": 3, "player_id": 3, "name": "Defender", "rating": 75, "position": "CB"},
        },
    }


def test_resolve_shot_action_shoots_on_non_negative_quality_bias_and_passes_otherwise():
    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig(), quality_bias=5)
    assert event["payload"]["action"] == "shoot"

    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig(), quality_bias=-6)
    assert event["payload"]["action"] == "pass"


def test_resolve_shot_action_defaults_quality_bias_to_zero_which_shoots():
    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(), _FakeMatchConfig())
    assert event["payload"]["action"] == "shoot"


from app.services.club_tactical_matchup_service import ClubTacticalSide, build_side


def _fake_side(rating: int = 75, mentality: str = "BALANCED", playstyle: str = "CENTRAL_PLAY") -> ClubTacticalSide:
    from dataclasses import dataclass as _dc

    from app.models.enums import Rarity

    @_dc
    class _P:
        position: object
        rating: int
        display_name: str = "Test Player"  # _card_to_actor reads this
        rarity: Rarity = Rarity.common  # calculate_base_strength reads this via RARITY_ORDER
        club: str = "Test FC"  # calculate_base_strength's chemistry-bonus Counter reads this
        country: str = "Testland"  # calculate_base_strength's chemistry-bonus Counter reads this

    @_dc
    class _C:
        id: int
        player: _P
        player_id: int = 0  # _card_to_actor reads this

    from app.services.club_formation_service import get_formation_slots

    # Paired with REAL FormationSlot objects (not None) — compute_profile's
    # team_strength field calls calculate_base_strength(cards_with_slots),
    # which reads slot.ideal_position/slot.category directly.
    slots = get_formation_slots("4-3-3")
    cards_with_slots = [(_C(id=100 + i, player_id=100 + i, player=_P(position=slot.ideal_position, rating=rating)), slot) for i, slot in enumerate(slots)]
    return build_side(cards_with_slots, mentality, playstyle)


def _hand_built_defense_moment(is_box: bool) -> dict:
    # _resolve_defense_tackle's body reads moment["shot_type"] unconditionally
    # (for its event payloads) alongside moment["is_box"] — both keys required.
    return {
        "minute": 10, "shot_type": "in_box" if is_box else "long_range", "is_box": is_box,
        "actors": {"defender": {"club_card_id": 3, "player_id": 3, "name": "D", "rating": 60, "position": "CB"}},
    }


def test_resolve_defense_tackle_reads_is_box_from_the_moment(monkeypatch):
    # random.random() forced to 0.0 makes every "random.random() < threshold"
    # check True (every configured min/max chance here is a positive float),
    # so the foul roll, the red-card roll, and (in the box branch) the
    # penalty-save roll are all forced True — isolates the actual is_box
    # branch under test from those other rolls. A wrong `if is_box:` (e.g.
    # inverted) would make one of the two assertions below fail, unlike the
    # old assertion that accepted either branch's outcomes.
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)

    event, _scorer, _card = engine._resolve_defense_tackle("a", _hand_built_defense_moment(is_box=True), _FakeMatchConfig())
    assert event["payload"]["is_penalty"] is True

    event, _scorer, _card = engine._resolve_defense_tackle("a", _hand_built_defense_moment(is_box=False), _FakeMatchConfig())
    assert event["event_type"] == "foul_stopped"
    assert event["payload"]["is_penalty"] is False


def test_simulate_match_with_tactical_sides_produces_a_valid_result():
    side_a, side_b = _fake_side(), _fake_side(rating=70)
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 70, "position": "ST", "category": "FWD"} for i in range(11)]

    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig())
    assert result.event_log  # sanity: there is something to check — 40-70 real phases reliably promote at least one chance
    assert result.score_a >= 0 and result.score_b >= 0
    for event in result.event_log:
        assert event["description"]


def test_simulate_match_records_red_card_and_injury_availability(monkeypatch):
    # Force every phase to resolve to a controlled, non-empty-net shot
    # chance, stub _resolve_shot_action to always report "blocked" (never a
    # goal, so score bookkeeping stays out of the way), stub
    # _resolve_defense_tackle to always hand back a red card for a known
    # club_card_id, and force random.random() low so both the post-shot 15%
    # foul-check gate and the 30% injury gate always fire. Unlike the
    # pre-refactor version of this test, random.choices can no longer shape
    # which moments get generated — the new simulate_match builds its moments
    # from real Chance objects produced by
    # club_tactical_matchup_service.simulate_match_phases, so that function
    # itself is stubbed to hand back a controlled Chance list instead.
    from app.services.club_tactical_matchup_service import Chance

    fake_chances = [Chance(attacking_side="a", minute=10, quality="NORMAL", shot_type="in_box", is_box=True)]

    def fake_resolve_shot_action(attacking_side, moment, config, quality_bias=0):
        event = {
            "minute": moment["minute"], "event_type": "blocked", "team": attacking_side,
            "payload": {"shot_type": moment["shot_type"], "action": "shoot", "shooter": "X", "missed": False, "blocked": True},
        }
        return event, "none"

    def fake_resolve_defense_tackle(defending_side, moment, config):
        event = {
            "minute": moment["minute"], "event_type": "foul_stopped", "team": defending_side,
            "payload": {"shot_type": moment["shot_type"], "action": "tackle", "defender": "Y", "card": "red", "is_penalty": False},
        }
        return event, "none", (999, "red")

    monkeypatch.setattr(engine.club_tactical_matchup_service, "simulate_match_phases", lambda side_a, side_b, config: fake_chances)
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)
    monkeypatch.setattr(engine, "_resolve_shot_action", fake_resolve_shot_action)
    monkeypatch.setattr(engine, "_resolve_defense_tackle", fake_resolve_defense_tackle)

    side_a, side_b = _fake_side(), _fake_side()
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig())

    assert result.red_cards, "expected at least one red card to be recorded"
    assert all(club_card_id == 999 and rounds == 1 for club_card_id, rounds in result.red_cards)
    assert result.injuries, "expected at least one injury to be recorded"
    assert all(club_card_id == 999 for club_card_id, _rounds in result.injuries)


def test_simulate_match_produces_a_deterministic_score_from_event_log(monkeypatch):
    # 0.99, not 0.0 — every _lerp_chance/_lerp_chance_positive threshold this
    # engine uses tops out around ~0.75 (match_keeper_save_chance_max), so
    # forcing random.random() to 0.99 makes every "random.random() < threshold"
    # check False, which is what drives every resolved chance to a goal
    # (missed=False, blocked=False, saved=False -> outcome="goal") — same
    # trick the pre-refactor version of this test used. random.random() is
    # shared process-wide (both this module's and club_tactical_matchup_service's
    # `import random` bind the same module object), so this also forces every
    # initiative check to go the same way — harmless here since the test only
    # asserts on goal-count consistency, not on which side attacks.
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)
    side_a, side_b = _fake_side(), _fake_side()
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig())
    assert result.event_log  # sanity: there is something to check
    goals_in_log = sum(1 for e in result.event_log if e["event_type"] == "goal")
    assert goals_in_log == result.score_a + result.score_b


def test_simulate_match_events_carry_real_club_name_descriptions():
    side_a, side_b = _fake_side(), _fake_side()
    lineup_a = [{"club_card_id": 100 + i, "player_id": 100 + i, "name": f"A{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    lineup_b = [{"club_card_id": 200 + i, "player_id": 200 + i, "name": f"B{i}", "rating": 75, "position": "ST", "category": "FWD"} for i in range(11)]
    result = engine.simulate_match(side_a, side_b, lineup_a, lineup_b, _FakeMatchConfig(), "Реал Мадрид", "Барселона")
    assert result.event_log  # sanity: there is something to check
    for event in result.event_log:
        assert isinstance(event["description"], str) and event["description"]
        club_name = "Реал Мадрид" if event["team"] == "a" else "Барселона"
        assert club_name in event["description"]


def test_describe_event_uses_tactic_flavor_for_a_high_quality_goal():
    import random
    from app.services import tournament_match_engine as engine

    random.seed(1)
    descriptions = {
        engine._describe_event("goal", "a", "Клуб А", "Клуб Б", playstyle="COUNTER_ATTACK", quality="VERY_HIGH")
        for _ in range(50)
    }
    # Over 50 draws, at least one COUNTER_ATTACK-flavored template must have
    # been picked — the flavor pool is mixed with the generic pool (spec
    # §11: "occasionally tactic-flavored", not every single goal), so this
    # asserts the flavor CAN appear, not that every draw uses it.
    assert any("контратак" in d.lower() for d in descriptions)


def test_describe_event_ignores_playstyle_for_a_low_quality_goal():
    import random
    from app.services import tournament_match_engine as engine

    random.seed(1)
    descriptions = {
        engine._describe_event("goal", "a", "Клуб А", "Клуб Б", playstyle="COUNTER_ATTACK", quality="LOW")
        for _ in range(50)
    }
    # LOW quality never gets tactic flavor (spec's examples are all
    # standout-moment phrasing) — every description must be one of the
    # original 3 generic goal templates.
    assert descriptions <= {
        "⚽ Гол! Клуб А открывает счёт!", "⚽ ГОЛ! Клуб А забивает!", "⚽ Клуб А находит путь в ворота!",
    }


def test_describe_event_still_works_with_no_playstyle_or_quality_passed():
    from app.services import tournament_match_engine as engine

    description = engine._describe_event("tackle_won", "b", "Клуб А", "Клуб Б")
    assert "Клуб Б" in description
