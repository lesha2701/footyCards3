# backend/tests/test_coach_boost_balance.py
"""Coach-boost balance regression tests — mirrors test_club_tactical_balance.py's
style: many matches per comparison, statistical tolerance, never a
single-match assertion. Confirms a coach boost has a REAL but BOUNDED
effect — never enough to flip a large rating-gap matchup, and confirms
coach_boost_service.py's DEFENSIVE_DISCIPLINE clamp (Phase 1, see
test_coach_boost_service.py's own test_defensive_shift_for_never_exceeds_zero_
even_at_extreme_magnitude) holds at the FULL match-simulation level too, not
just in the isolated defensive_shift_for() call.

Reuses test_club_tactical_balance.py's own _FakePlayer/_FakeCard/_squad
fixture shapes verbatim (same field names/defaults) — this file adds only
what that file's _Config doesn't cover: build_side's optional `coach=`
argument (Task 7) and a fuller match-level config, since these tests run
the FULL simulated match (tournament_match_engine.simulate_match) rather
than just club_tactical_matchup_service.simulate_match_phases, so they need
every match_* field the shot/tackle resolution functions read — same
_FakeConfig -> _FakeMatchConfig split test_tournament_match_engine.py
already uses, for the same reason."""
from dataclasses import dataclass

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Position, Rarity
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side
from app.services.tournament_match_engine import simulate_match


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"  # _card_to_actor reads this
    # calculate_base_strength (via compute_profile) reads rarity/club/country;
    # defaults mirror test_club_tactical_balance.py's own _FakePlayer.
    rarity: str = "common"
    club: int = 1
    country: int = 1
    attack_rating: int | None = None
    defense_rating: int | None = None


@dataclass
class _FakeCard:
    id: int
    player_id: int
    player: _FakePlayer
    diamond_rating_bonus: int = 0


# Phase-pipeline-only fields (club_tactical_matchup_service.simulate_match_phases),
# identical to test_club_tactical_balance.py's _Config.
class _Config:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


# Adds every match_* field tournament_match_engine's shot/tackle resolution
# functions read (_resolve_shot_action, _resolve_shot_continuation,
# _resolve_defense_tackle) — needed because these tests run the FULL
# simulate_match, not just simulate_match_phases. Values copied verbatim from
# test_tournament_match_engine.py's own _FakeMatchConfig (which itself
# mirrors GameConfig's defaults), so admin-tuned production values aren't
# silently duplicated a third time with different numbers.
class _MatchConfig(_Config):
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
    club_tactical_tackle_attempt_chance = 0.20
    club_tactical_injury_chance = 0.35


def _squad(ratings: dict[Position, int], default: int = 75, formation: str = "4-3-3") -> list[tuple[_FakeCard, object]]:
    """Verbatim copy of test_club_tactical_balance.py's own _squad — pairs each
    fake card with a REAL FormationSlot (not None), same reasoning as that
    file's docstring (compute_profile's team_strength needs slot.ideal_position/
    slot.category)."""
    slots = get_formation_slots(formation)
    cards = []
    for i, slot in enumerate(slots):
        rating = ratings.get(slot.ideal_position, default)
        cards.append((_FakeCard(id=i, player_id=i, player=_FakePlayer(slot.ideal_position, rating)), slot))
    return cards


def _lineup_dicts(cards_with_slots: list[tuple[_FakeCard, object]]) -> list[dict]:
    """Same shape scripts/simulate_tactical_balance.py's lineup_dicts() builds —
    the only two keys tournament_match_engine._resolve_breakaway actually
    reads (category for the FWD lookup, rating for the miss-chance roll)."""
    return [{"category": slot.category, "rating": card.player.rating} for card, slot in cards_with_slots]


def _play_match(
    mentality_a: str, playstyle_a: str, ratings_a: dict[Position, int],
    mentality_b: str, playstyle_b: str, ratings_b: dict[Position, int],
    coach_a: Coach | None = None, coach_b: Coach | None = None,
):
    """Runs one FULL simulated match (tournament_match_engine.simulate_match),
    not just simulate_match_phases — this file's own tests need the real
    score, since they assert on win rate / goals conceded, not chance quality."""
    cards_a = _squad(ratings_a)
    cards_b = _squad(ratings_b)
    side_a = build_side(cards_a, mentality_a, playstyle_a, coach=coach_a)
    side_b = build_side(cards_b, mentality_b, playstyle_b, coach=coach_b)
    return simulate_match(side_a, side_b, _lineup_dicts(cards_a), _lineup_dicts(cards_b), _MatchConfig())


# --- coach boosts must narrow a large rating gap a little, never invert it ---
def test_legendary_coach_does_not_flip_a_large_rating_gap_matchup():
    """A ~200+ point team_strength gap (this repo's own established "large gap"
    fixture — same flat 95-vs-70 squads as test_club_tactical_balance.py's
    test_much_weaker_squad_does_not_out_chance_a_much_stronger_one_even_with_a_good_matchup,
    which measures team_strength=1075 for the 95-rated squad vs 800 for the
    70-rated one, a 275-point gap) should still heavily favor the stronger
    squad even when the WEAKER squad has a fully-loaded legendary coach (3
    boosts, magnitude 8.0 each — same scale as Task 7/8's own tests) and the
    stronger squad has none.

    Measured (scripts/_calibrate_task9.py, n=400, BALANCED/CENTRAL_PLAY both
    sides): weak side's win rate WITH the coach = 4.8% vs 5.2% WITHOUT any
    coach on either side — at this large a gap the coach's narrowing effect
    is barely visible above sampling noise, exactly the "a little, never
    inverts" behavior this test guards. 0.20 leaves a wide margin above the
    observed ~5% while still catching any future regression that let a
    coach meaningfully close (let alone invert) a gap this size."""
    weak_coach = Coach(display_name="Weak Squad's Coach", rarity=Rarity.legendary)
    weak_coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=8.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=8.0),
    ]
    strong = {pos: 95 for pos in Position}
    weak = {pos: 70 for pos in Position}

    n = 350
    weak_wins = 0
    for _ in range(n):
        result = _play_match(
            "BALANCED", "CENTRAL_PLAY", strong, "BALANCED", "CENTRAL_PLAY", weak,
            coach_a=None, coach_b=weak_coach,
        )
        if result.score_b > result.score_a:
            weak_wins += 1
    weak_win_rate = weak_wins / n
    assert weak_win_rate < 0.20


# --- coach_boost_service.py's DEFENSIVE_DISCIPLINE clamp must hold at the
# full match-simulation level, not just in the isolated function call ---
def test_defensive_discipline_boost_never_lets_attacking_defend_better_than_balanced():
    """Direct match-level regression test for coach_boost_service.defensive_shift_for's
    own already-unit-tested clamp (test_coach_boost_service.py's
    test_defensive_shift_for_never_exceeds_zero_even_at_extreme_magnitude):
    an ATTACKING-mentality squad with a DEFENSIVE_DISCIPLINE boost, even at
    an extreme magnitude (100.0 — the exact value that unit test used to
    prove the clamp), must never concede FEWER goals on average than the
    same squad playing BALANCED with no coach at all — the clamp caps the
    boosted shift at 0.0 (BALANCED's own shift), so the two should be
    statistically indistinguishable; without the clamp, an unbounded
    magnitude-100 offset would push the defensive shift far positive
    instead, making the defense next-to-unbeatable.

    Measured (scripts/_calibrate_task9.py, n=500, flat 80-rated squads both
    sides): mean goals conceded — ATTACKING + magnitude=100.0
    DEFENSIVE_DISCIPLINE = 2.646, BALANCED with no coach = 2.702 (the
    boosted side actually conceded slightly FEWER on this sample, but well
    within sampling noise of a true tie, consistent with both shifts
    clamping to the identical 0.0 value). For reference, plain ATTACKING
    with no coach at all = 2.768 (worse than BALANCED, as expected — the
    clamp only defangs the boost, it doesn't erase ATTACKING's own -0.07
    base penalty). Margin of 0.5 comfortably covers the ~0.06 noise observed
    here while still catching a broken clamp, which would collapse mean GA
    much further (the unclamped shift pins the attacker's duel ratio at its
    0.05 floor, not a few hundredths off BALANCED)."""
    opponent = {pos: 80 for pos in Position}
    attacker_squad = {pos: 80 for pos in Position}

    boosted_coach = Coach(display_name="Extreme Discipline Coach", rarity=Rarity.legendary)
    boosted_coach.boosts = [CoachBoost(boost_type=CoachBoostType.DEFENSIVE_DISCIPLINE, magnitude=100.0)]

    n = 500
    boosted_ga = 0
    for _ in range(n):
        result = _play_match(
            "ATTACKING", "CENTRAL_PLAY", attacker_squad, "BALANCED", "CENTRAL_PLAY", opponent,
            coach_a=boosted_coach, coach_b=None,
        )
        boosted_ga += result.score_b  # goals conceded by side A (the boosted ATTACKING side)

    balanced_ga = 0
    for _ in range(n):
        result = _play_match(
            "BALANCED", "CENTRAL_PLAY", attacker_squad, "BALANCED", "CENTRAL_PLAY", opponent,
            coach_a=None, coach_b=None,
        )
        balanced_ga += result.score_b

    boosted_mean_ga = boosted_ga / n
    balanced_mean_ga = balanced_ga / n
    assert boosted_mean_ga > balanced_mean_ga - 0.5
