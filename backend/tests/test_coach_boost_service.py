from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Rarity
from app.services.coach_boost_service import (
    apply_zone_boosts,
    arena_category_bonus,
    arena_pass_fail_chance_reduction,
    arena_team_strength_bonus,
    defensive_shift_for,
    depth_bonus_cap_for,
    first_pass_input_bonus,
    initiative_mult_for,
    resolve_active_boosts,
    transition_bonus_for,
)


def _coach(*boosts: tuple[CoachBoostType, float]) -> Coach:
    coach = Coach(display_name="Fixture Coach", rarity=Rarity.legendary)
    coach.boosts = [CoachBoost(boost_type=bt, magnitude=mag) for bt, mag in boosts]
    return coach


def test_resolve_active_boosts_of_none_is_empty():
    boosts = resolve_active_boosts(None)
    assert boosts.by_type == {}


def test_resolve_active_boosts_reads_each_coach_boost():
    coach = _coach((CoachBoostType.ATTACK_CENTRAL, 4.0), (CoachBoostType.GOALKEEPING, 6.0))
    boosts = resolve_active_boosts(coach)
    assert boosts.by_type == {CoachBoostType.ATTACK_CENTRAL: 4.0, CoachBoostType.GOALKEEPING: 6.0}


def test_apply_zone_boosts_adds_to_matching_zones_only():
    boosts = resolve_active_boosts(_coach((CoachBoostType.ATTACK_CENTRAL, 5.0)))
    zone_values = {"central_attack": 70.0, "wing_attack": 70.0, "midfield_control": 70.0}
    result = apply_zone_boosts(zone_values, boosts)
    assert result["central_attack"] == 75.0
    assert result["wing_attack"] == 70.0
    assert result["midfield_control"] == 70.0


def test_apply_zone_boosts_is_a_no_op_with_no_coach():
    zone_values = {"central_attack": 70.0}
    assert apply_zone_boosts(zone_values, resolve_active_boosts(None)) == zone_values


def test_depth_bonus_cap_for_adds_squad_stability():
    boosts = resolve_active_boosts(_coach((CoachBoostType.SQUAD_STABILITY, 2.0)))
    assert depth_bonus_cap_for(6.0, boosts) == 8.0
    assert depth_bonus_cap_for(6.0, resolve_active_boosts(None)) == 6.0


def test_initiative_mult_for_adds_ball_control():
    boosts = resolve_active_boosts(_coach((CoachBoostType.BALL_CONTROL, 0.1)))
    assert round(initiative_mult_for(1.0, boosts), 4) == 1.1
    assert initiative_mult_for(1.0, resolve_active_boosts(None)) == 1.0


def test_defensive_shift_for_only_applies_to_attacking_mentality():
    boosts = resolve_active_boosts(_coach((CoachBoostType.DEFENSIVE_DISCIPLINE, 0.03)))
    assert round(defensive_shift_for("ATTACKING", -0.07, boosts), 4) == -0.04
    assert defensive_shift_for("BALANCED", 0.0, boosts) == 0.0
    assert defensive_shift_for("DEFENSIVE", 0.09, boosts) == 0.09


def test_defensive_shift_for_never_exceeds_zero_even_at_extreme_magnitude():
    # Regression test for this session's own "extreme values inverted a
    # matchup" lesson: no coach boost should let ATTACKING defend better
    # than BALANCED (0.0) purely from a coach, regardless of magnitude.
    boosts = resolve_active_boosts(_coach((CoachBoostType.DEFENSIVE_DISCIPLINE, 100.0)))
    assert defensive_shift_for("ATTACKING", -0.07, boosts) == 0.0


def test_transition_bonus_for_only_applies_to_counter_attack_playstyle():
    boosts = resolve_active_boosts(_coach((CoachBoostType.COUNTER_MASTERY, 0.3)))
    assert round(transition_bonus_for("COUNTER_ATTACK", 2.0, boosts), 4) == 2.3
    assert transition_bonus_for("HIGH_PRESS", 1.3, boosts) == 1.3


def test_first_pass_input_bonus_reads_passing_accuracy():
    boosts = resolve_active_boosts(_coach((CoachBoostType.PASSING_ACCURACY, 3.0)))
    assert first_pass_input_bonus(boosts) == 3.0
    assert first_pass_input_bonus(resolve_active_boosts(None)) == 0.0


def test_arena_category_bonus_maps_fwd_def_gk_only():
    boosts = resolve_active_boosts(_coach(
        (CoachBoostType.ATTACK_CENTRAL, 4.0), (CoachBoostType.DEFENCE_CENTRAL, 6.0), (CoachBoostType.GOALKEEPING, 8.0),
    ))
    assert arena_category_bonus("FWD", boosts) == 4
    assert arena_category_bonus("DEF", boosts) == 6
    assert arena_category_bonus("GK", boosts) == 8
    assert arena_category_bonus("MID", boosts) == 0


def test_arena_pass_fail_chance_reduction_reads_passing_accuracy():
    boosts = resolve_active_boosts(_coach((CoachBoostType.PASSING_ACCURACY, 2.0)))
    assert arena_pass_fail_chance_reduction(boosts) == 2.0


def test_arena_team_strength_bonus_reads_midfield_control():
    boosts = resolve_active_boosts(_coach((CoachBoostType.MIDFIELD_CONTROL, 5.0)))
    assert arena_team_strength_bonus(boosts) == 5
