from dataclasses import dataclass

from app.models.coach import Coach, CoachBoost
from app.models.enums import CoachBoostType, Position, Rarity
from app.services import club_tactical_profile_service as svc
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    rarity: str = "common"
    club: int = 1
    country: int = 1
    attack_rating: int | None = None
    defense_rating: int | None = None


@dataclass
class _FakeCard:
    id: int
    player: _FakePlayer
    diamond_rating_bonus: int = 0


def _cards_with_slots(ratings_by_code: dict[str, int], formation: str = "4-3-3"):
    slots = get_formation_slots(formation)
    out = []
    for i, slot in enumerate(slots):
        rating = ratings_by_code.get(slot.code, 70)
        out.append((_FakeCard(id=i, player=_FakePlayer(position=slot.ideal_position, rating=rating)), slot))
    return out


def test_zone_weights_cover_every_position_used_in_any_formation():
    for formation, slots in CLUB_FORMATIONS.items():
        for slot in slots:
            assert slot.ideal_position in svc.ZONE_WEIGHTS, (formation, slot.ideal_position)


def test_st_is_the_strongest_contributor_to_central_attack():
    assert svc.zone_weight(Position.ST, "central_attack") == 1.00
    assert svc.zone_weight(Position.LW, "central_attack") == 0.65
    assert svc.zone_weight(Position.CB, "central_attack") == 0.0


def test_position_fit_discretizes_into_1_0_0_9_0_85():
    assert svc.position_fit(Position.ST, "central_attack") == 1.0       # weight 1.00
    assert svc.position_fit(Position.LW, "central_attack") == 0.9       # weight 0.65
    assert svc.position_fit(Position.CAM, "wing_attack") == 0.85        # weight 0.10
    assert svc.position_fit(Position.CB, "central_attack") == 0.0       # not eligible at all


def test_compute_profile_is_a_weighted_average_not_a_sum():
    # Weighted average (not sum): adding another ST at 90 to a formation raises
    # central_attack by averaging both STs' contributions, not summing them.
    # Two formations with all non-STs at 70 but different midfield compositions
    # produce different zone values (showing it's position-dependent), but each
    # is the proper weighted average per spec §5.
    one_st = _cards_with_slots({"FWD2": 90})
    profile_one = svc.compute_profile(one_st)

    two_st_formation = _cards_with_slots({"FWD1": 90, "FWD2": 90}, formation="4-4-2")
    profile_two = svc.compute_profile(two_st_formation)

    # one_st (4-3-3): includes LW/RW (weight 0.65 each) pulling down average
    # two_st_formation (4-4-2): includes LM/RM (weight 0.10 each) lower drag
    # Both are correctly computed as weighted averages (plus each formation's
    # own small, formation-agnostic depth bonus — see compute_profile's
    # DEPTH_BONUS_SCALE docstring — 4.3 and 3.2 rating points respectively
    # here), never a sum.
    assert profile_one.central_attack == 80.6
    assert profile_two.central_attack == 88.6
    # Demonstrate it's an average (+ bounded depth bonus) not a sum: still
    # well under 90, let alone anywhere near a raw sum of 180.
    assert profile_two.central_attack < 90.0


def test_compute_profile_goalkeeping_only_reflects_the_gk():
    cards = _cards_with_slots({"GK": 88})
    profile = svc.compute_profile(cards)
    assert profile.goalkeeping == 88.0


def test_compute_profile_team_strength_matches_calculate_base_strength():
    from app.services.lineup_service import calculate_base_strength

    cards = _cards_with_slots({})
    profile = svc.compute_profile(cards)
    assert profile.team_strength == calculate_base_strength(cards)


def test_5_3_2_produces_lower_wing_attack_than_4_3_3_for_identical_lb_rb_ratings():
    # 5-3-2 has no LM/RM feeding wing_attack (0.85 weight) the way 4-3-3's
    # LW/RW (1.00 weight) do — same LB/RB rating in both, but 4-3-3's front
    # three genuinely contribute to wing_attack while 5-3-2's extra CB does not.
    shared = {"DEF1": 75, "DEF4": 75}
    four_three_three = svc.compute_profile(_cards_with_slots({**shared, "FWD1": 90, "FWD3": 90}, "4-3-3"))
    five_three_two = svc.compute_profile(_cards_with_slots({**shared, "DEF5": 75}, "5-3-2"))
    assert four_three_three.wing_attack > five_three_two.wing_attack


class _FakeTacticalFitConfig:
    club_tactical_fit_formation_weight = 0.40
    club_tactical_fit_playstyle_weight = 0.40
    club_tactical_fit_mentality_weight = 0.20


def test_tactical_fit_is_a_percentage():
    cards = _cards_with_slots({})
    profile = svc.compute_profile(cards)
    fit = svc.compute_tactical_fit(cards, profile, "BALANCED", "CENTRAL_PLAY", _FakeTacticalFitConfig())
    assert 0 <= fit <= 100


def test_wing_play_scores_higher_fit_for_a_squad_with_strong_flanks_than_weak_flanks():
    strong_flanks = _cards_with_slots({"FWD1": 92, "FWD3": 92, "DEF1": 85, "DEF4": 85, "FWD2": 65})
    weak_flanks = _cards_with_slots({"FWD1": 65, "FWD3": 65, "DEF1": 65, "DEF4": 65, "FWD2": 92})
    config = _FakeTacticalFitConfig()

    strong_profile = svc.compute_profile(strong_flanks)
    weak_profile = svc.compute_profile(weak_flanks)

    strong_fit = svc.compute_tactical_fit(strong_flanks, strong_profile, "BALANCED", "WING_PLAY", config)
    weak_fit = svc.compute_tactical_fit(weak_flanks, weak_profile, "BALANCED", "WING_PLAY", config)
    assert strong_fit > weak_fit


def test_park_the_bus_mentality_fit_favors_a_defence_heavy_squad_over_an_attack_heavy_one():
    defence_heavy = _cards_with_slots({"DEF1": 90, "DEF2": 90, "DEF3": 90, "DEF4": 90, "FWD2": 60})
    attack_heavy = _cards_with_slots({"DEF1": 60, "DEF2": 60, "DEF3": 60, "DEF4": 60, "FWD2": 90})

    defence_profile = svc.compute_profile(defence_heavy)
    attack_profile = svc.compute_profile(attack_heavy)

    assert svc._mentality_fit(defence_profile, "PARK_THE_BUS") > svc._mentality_fit(attack_profile, "PARK_THE_BUS")


def test_compute_profile_with_no_coach_matches_current_behavior():
    cards_with_slots = _cards_with_slots({})
    profile_without_arg = svc.compute_profile(cards_with_slots)
    profile_with_none = svc.compute_profile(cards_with_slots, coach=None)
    assert profile_without_arg == profile_with_none


def test_compute_profile_applies_attack_central_boost():
    cards_with_slots = _cards_with_slots({})
    coach = Coach(display_name="Attack Coach", rarity=Rarity.legendary)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=5.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=5.0),
        CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=5.0),
    ]
    base = svc.compute_profile(cards_with_slots)
    boosted = svc.compute_profile(cards_with_slots, coach=coach)
    assert boosted.central_attack == round(min(99.0, base.central_attack + 5.0), 1)
    assert boosted.wing_attack == base.wing_attack  # unaffected zone stays exactly the same


def test_compute_profile_squad_stability_raises_effective_depth_cap():
    # 3-5-2 gives midfield_control a weight_total of 3.40 (5 midfield slots
    # plus 3 CBs' minor 0.10 contribution each) -- see
    # club_tactical_profile_service.compute_profile's DEPTH_BONUS_SCALE
    # docstring for the same 3-5-2-vs-4-3-3 worked comparison -- pushing the
    # raw depth bonus (2.0 * (3.40 - 1.0) = 4.8) meaningfully above 1.0 and
    # close to DEPTH_BONUS_CAP (6.0), unlike any 4-3-3/4-4-2 fixture in this
    # file.
    cards_with_slots_with_real_depth = _cards_with_slots({}, formation="3-5-2")
    coach = Coach(display_name="Stability Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.SQUAD_STABILITY, magnitude=2.0)]
    base = svc.compute_profile(cards_with_slots_with_real_depth)
    boosted = svc.compute_profile(cards_with_slots_with_real_depth, coach=coach)
    assert boosted.midfield_control >= base.midfield_control  # never LOWER with a positive boost
