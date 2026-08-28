import random

from app.services import tournament_match_engine as engine


def _fake_lineup(club_id: int):
    """A minimal fake lineup: list of (club_card_id, player_id, name, rating, position, category) tuples,
    one per FORMATION_SLOTS category, enough for _pick_actor to find candidates in every category."""
    return [
        {"club_card_id": club_id * 100 + i, "player_id": club_id * 100 + i, "name": f"Player{club_id}-{i}",
         "rating": 70, "position": pos, "category": cat}
        for i, (cat, pos) in enumerate([
            ("GK", "GK"), ("DEF", "CB"), ("DEF", "CB"), ("DEF", "LB"), ("DEF", "RB"),
            ("MID", "CDM"), ("MID", "CM"), ("MID", "CAM"), ("FWD", "LW"), ("FWD", "ST"), ("FWD", "RW"),
        ])
    ]


class _FakeConfig:
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def test_moment_queue_has_between_14_and_22_moments():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    assert 14 <= len(moments) <= 22


def test_shot_moments_pick_real_actors_from_both_sides():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    shot_moments = [m for m in moments if m["kind"] == "shot" and m["shot_type"] != "empty_net"]
    assert shot_moments  # with 14-22 moments and the existing shot-chance weight, at least one is virtually certain
    for m in shot_moments:
        attacking_lineup = lineup_a if m["attacking_side"] == "a" else lineup_b
        defending_lineup = lineup_b if m["attacking_side"] == "a" else lineup_a
        attacking_ids = {a["club_card_id"] for a in attacking_lineup}
        defending_ids = {a["club_card_id"] for a in defending_lineup}
        assert m["actors"]["shooter"]["club_card_id"] in attacking_ids
        assert m["actors"]["pass_target"]["club_card_id"] in attacking_ids
        assert m["actors"]["defender"]["club_card_id"] in defending_ids
        for actor in m["actors"].values():
            # Exact shape, not just a superset — _pick_actor trims to exactly
            # the documented Actor keys regardless of what the source lineup
            # entry carries (e.g. a fixture's extra "category" key).
            assert set(actor.keys()) == {"club_card_id", "player_id", "name", "rating", "position"}


def test_stronger_side_attacks_more_often(monkeypatch):
    monkeypatch.setattr(engine.random, "sample", lambda pop, k: list(range(1, k + 1)))
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(140, 10, _FakeConfig(), lineup_a, lineup_b)
    attacking_a = sum(1 for m in moments if m["attacking_side"] == "a")
    assert attacking_a > len(moments) / 2


def test_empty_net_shot_moment_has_no_actors_and_no_defense_situation_id():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moment = engine._build_shot_moment(10, lineup_a, lineup_b, "a", "empty_net")
    assert moment["kind"] == "shot"
    assert moment["shot_type"] == "empty_net"
    assert moment["situation_kind"] == "breakaway"
    assert moment["situation_id"] is None
    assert moment["actors"] == {}
    assert "defense_situation_id" not in moment


# _FakeMatchConfig exposes every match_* field the resolution code (Task 11)
# reads, mirroring GameConfig's defaults (see app/models/game_config.py) —
# _FakeConfig above only covers the shot-type weights generate_moment_queue
# (Task 10) needs, so this subclass adds the rest rather than duplicating them.
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


def test_simulate_match_produces_deterministic_score_from_event_log(monkeypatch):
    # Force every shot to score: all miss/save/block/foul rolls fail — every
    # _lerp_chance/_lerp_chance_positive threshold used in resolution tops
    # out at 0.75 (match_keeper_save_chance_max), comfortably below 0.99, so
    # every "random.random() < threshold" check is False and every shot
    # resolves to a goal.
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())
    goals_in_log = sum(1 for e in result.event_log if e["event_type"] == "goal")
    assert goals_in_log == result.score_a + result.score_b
    assert result.score_a >= 0 and result.score_b >= 0


def _hand_built_moment(situation) -> dict:
    """A minimal, fully-formed shot moment for exercising _resolve_shot_action
    directly — bypasses generate_moment_queue's random lottery so the action
    policy (shoot iff situation.bias >= 0) is exercised deterministically
    rather than hoping a random moment queue happens to produce a usable
    sample of both bias signs."""
    return {
        "minute": 10,
        "situation_id": situation.id,
        "shot_type": situation.shot_type,
        "actors": {
            "shooter": {"club_card_id": 1, "player_id": 1, "name": "Shooter", "rating": 75, "position": "ST"},
            "pass_target": {"club_card_id": 2, "player_id": 2, "name": "PassTarget", "rating": 75, "position": "CAM"},
            "defender": {"club_card_id": 3, "player_id": 3, "name": "Defender", "rating": 75, "position": "CB"},
        },
    }


def test_resolve_shot_action_follows_default_shoot_pass_policy_by_bias():
    # Directly exercises _resolve_shot_action's action policy — shoot when
    # the situation's bias is non-negative, pass otherwise — using two real
    # AttackSituations with known bias signs, rather than going through
    # simulate_match's random moment queue and hoping it samples both cases.
    positive_situation = engine.ATTACK_SITUATIONS_BY_ID["att_box_through_ball"]
    negative_situation = engine.ATTACK_SITUATIONS_BY_ID["att_box_narrow_angle"]
    assert positive_situation.bias >= 0
    assert negative_situation.bias < 0

    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(positive_situation), _FakeMatchConfig())
    assert event["payload"]["action"] == "shoot"

    event, _scorer = engine._resolve_shot_action("a", _hand_built_moment(negative_situation), _FakeMatchConfig())
    assert event["payload"]["action"] == "pass"


def test_simulate_match_records_red_card_and_injury_availability(monkeypatch):
    # Force every tackle to foul with a red card, and every breakaway to injure —
    # deterministic via monkeypatching the specific roll functions rather than
    # blanket-forcing random.random(), since a blanket force also forces misses.
    # Strategy: force every moment to be a non-empty-net shot chance, stub
    # _resolve_shot_action to always report "blocked" (never a goal, so score
    # bookkeeping stays out of the way), stub _resolve_defense_tackle to
    # always hand back a red card for a known club_card_id, and force
    # random.random() low so both the post-shot 15% foul-check gate and the
    # 30% injury gate always fire.
    def fake_choices(population, weights=None, k=1):
        if "shot_chance" in population:
            return ["shot_chance"]
        return [population[0]]  # SHOT_TYPES[0] == "in_box" — never empty_net

    def fake_resolve_shot_action(attacking_side, moment, config):
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

    monkeypatch.setattr(engine.random, "choices", fake_choices)
    monkeypatch.setattr(engine.random, "random", lambda: 0.0)
    monkeypatch.setattr(engine, "_resolve_shot_action", fake_resolve_shot_action)
    monkeypatch.setattr(engine, "_resolve_defense_tackle", fake_resolve_defense_tackle)

    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())

    assert result.red_cards, "expected at least one red card to be recorded"
    assert all(club_card_id == 999 and rounds == 1 for club_card_id, rounds in result.red_cards)
    assert result.injuries, "expected at least one injury to be recorded"
    assert all(club_card_id == 999 for club_card_id, _rounds in result.injuries)


def test_simulate_match_events_carry_club_name_descriptions(monkeypatch):
    monkeypatch.setattr(engine.random, "random", lambda: 0.99)  # every roll fails -> every shot scores, same trick as the existing determinism test
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig(), "Реал Мадрид", "Барселона")

    assert result.event_log  # sanity: there is something to check
    for event in result.event_log:
        assert isinstance(event["description"], str) and event["description"]
        assert "Player" not in event["description"]  # never names an individual player, only the club
        club_name = "Реал Мадрид" if event["team"] == "a" else "Барселона"
        assert club_name in event["description"]


def test_simulate_match_default_club_names_when_omitted():
    # Existing two call sites in this file (test_simulate_match_produces_deterministic_score_from_event_log,
    # and the one further below) call simulate_match with only 5 positional args — confirms that keeps working
    # via the new params' defaults, not a breaking signature change.
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    result = engine.simulate_match(70, 70, lineup_a, lineup_b, _FakeMatchConfig())
    for event in result.event_log:
        assert event["description"]
