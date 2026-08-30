from dataclasses import dataclass

from app.models.enums import Position
from app.services import club_tactical_profile_service as svc
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    rarity: str = "common"
    club: int = 1
    country: int = 1


@dataclass
class _FakeCard:
    id: int
    player: _FakePlayer


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
    # Both are correctly computed as weighted averages, not sums.
    assert profile_one.central_attack == 76.3
    assert profile_two.central_attack == 85.4
    # Demonstrate it's an average not a sum: two_st_formation < 90 (not 180)
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
