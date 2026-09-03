# backend/tests/test_club_tactical_balance.py
from dataclasses import dataclass

from app.models.enums import Position
from app.services.club_formation_service import get_formation_slots
from app.services.club_tactical_matchup_service import build_side, simulate_match_phases


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"  # _card_to_actor reads this
    # calculate_base_strength (via compute_profile) reads rarity/club/country;
    # defaults mirror the fixture pattern used in test_club_tactical_matchup_service.py
    # and test_club_tactical_profile_service.py.
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


class _Config:
    club_tactical_phases_per_match_min = 40
    club_tactical_phases_per_match_max = 70
    club_tactical_promoted_chance_target_min = 15
    club_tactical_promoted_chance_target_max = 25
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def _squad(ratings: dict[Position, int], default: int = 75, formation: str = "4-3-3") -> list[tuple[_FakeCard, object]]:
    """Pairs each fake card with a REAL FormationSlot (not None) —
    compute_profile's team_strength field needs slot.ideal_position/
    slot.category, same reasoning as Task 9/10's equivalent fixtures."""
    slots = get_formation_slots(formation)
    cards = []
    for i, slot in enumerate(slots):
        rating = ratings.get(slot.ideal_position, default)
        cards.append((_FakeCard(id=i, player_id=i, player=_FakePlayer(slot.ideal_position, rating)), slot))
    return cards


def _chances_for(mentality_a, playstyle_a, ratings_a, mentality_b, playstyle_b, ratings_b, trials=40):
    a_total = b_total = 0
    quality_score = {"LOW": 1, "NORMAL": 2, "HIGH": 3, "VERY_HIGH": 4}
    a_quality_sum = b_quality_sum = 0
    for _ in range(trials):
        side_a = build_side(_squad(ratings_a), mentality_a, playstyle_a)
        side_b = build_side(_squad(ratings_b), mentality_b, playstyle_b)
        chances = simulate_match_phases(side_a, side_b, _Config())
        for c in chances:
            if c.attacking_side == "a":
                a_total += 1
                a_quality_sum += quality_score[c.quality]
            else:
                b_total += 1
                b_quality_sum += quality_score[c.quality]
    return a_total, a_quality_sum / a_total if a_total else 0, b_total, b_quality_sum / b_total if b_total else 0


# --- spec §14 item 1: two strong STs are better used under 4-4-2 than 4-3-3 ---
def test_two_strong_strikers_produce_higher_central_attack_in_4_4_2_than_4_3_3():
    from app.services.club_tactical_profile_service import compute_profile

    # 4-3-3 can only field one true ST (FWD2) — the second strong finisher
    # has to sit at LW instead, where its central_attack weight is only 0.65
    # (spec §5's table) instead of ST's full 1.00.
    squad_4_3_3 = _squad({Position.LW: 92, Position.ST: 92, Position.RW: 70}, formation="4-3-3")
    # 4-4-2 has two true ST slots, so both strong finishers get full weight.
    squad_4_4_2 = _squad({Position.ST: 92}, formation="4-4-2")

    assert compute_profile(squad_4_4_2).central_attack > compute_profile(squad_4_3_3).central_attack


# --- spec §14 item 4 (worked example): PARK_THE_BUS does not out-defend BALANCED for weak defenders ---
def test_park_the_bus_does_not_rescue_weak_defenders_against_elite_attackers():
    # Playstyle is held at CENTRAL_PLAY on the defending side in both calls —
    # "BALANCED" is a MENTALITY value, not a member of PLAYSTYLES, so it
    # cannot be passed as the playstyle argument (would KeyError inside
    # pick_progression_zone's PLAYSTYLE_ZONE_WEIGHTS[playstyle] lookup).
    # Mentality is the only varying factor between the two _chances_for calls.
    weak_def_ratings = {Position.CB: 64, Position.LB: 65, Position.RB: 66}
    elite_atk_ratings = {Position.ST: 95, Position.LW: 93, Position.RW: 94}

    bus_a, _bus_q, _bus_bt, bus_conceded_quality = _chances_for(
        "PARK_THE_BUS", "CENTRAL_PLAY", weak_def_ratings, "ATTACKING", "CENTRAL_PLAY", elite_atk_ratings,
    )
    balanced_a, _bal_q, _bal_bt, balanced_conceded_quality = _chances_for(
        "BALANCED", "CENTRAL_PLAY", weak_def_ratings, "ATTACKING", "CENTRAL_PLAY", elite_atk_ratings,
    )
    # PARK_THE_BUS must not produce a LOWER average conceded chance quality
    # than BALANCED by more than a token amount — the bus narrows exposure
    # (fewer total chances via low initiative) but the individual chances
    # that do get through remain just as dangerous, since defenders are
    # never rating-boosted (spec §6.5's worked check).
    assert balanced_conceded_quality - bus_conceded_quality < 0.5


# --- spec §14 item 7: a 70-rated squad does not beat a 95-rated squad even with a good tactical matchup ---
def test_much_weaker_squad_does_not_out_chance_a_much_stronger_one_even_with_a_good_matchup():
    # "DEFENSIVE" is a MENTALITY value, not a member of PLAYSTYLES — the
    # stronger side's playstyle here is CENTRAL_PLAY (a neutral choice,
    # isolating mentality+rating as the two variables under test).
    weak = {pos: 70 for pos in Position}
    strong = {pos: 95 for pos in Position}
    weak_total, _wq, strong_total, _sq = _chances_for(
        "ATTACKING", "COUNTER_ATTACK", weak, "PARK_THE_BUS", "CENTRAL_PLAY", strong,
    )
    assert strong_total >= weak_total


# --- spec §14 item 8: two identical squads simulate close to an even split ---
def test_identical_squads_on_identical_settings_split_close_to_even():
    ratings = {pos: 78 for pos in Position}
    a_total, _aq, b_total, _bq = _chances_for("BALANCED", "CENTRAL_PLAY", ratings, "BALANCED", "CENTRAL_PLAY", ratings, trials=60)
    total = a_total + b_total
    assert total > 0
    assert 0.35 < a_total / total < 0.65
