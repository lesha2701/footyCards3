from app.services import club_tactical_matchup_service as svc
from app.services.club_tactical_profile_service import TeamTacticalProfile


def _profile(**overrides) -> TeamTacticalProfile:
    base = dict(central_attack=70, wing_attack=70, midfield_control=70, central_defence=70, wing_defence=70, goalkeeping=70, team_strength=700)
    base.update(overrides)
    return TeamTacticalProfile(**base)


def test_mentalities_and_playstyles_registries_match_spec():
    assert svc.MENTALITIES == ("PARK_THE_BUS", "DEFENSIVE", "BALANCED", "ATTACKING")
    assert svc.PLAYSTYLES == ("WING_PLAY", "CENTRAL_PLAY", "POSSESSION", "HIGH_PRESS", "COUNTER_ATTACK")


def test_initiative_mult_table():
    assert svc.INITIATIVE_MULT == {"PARK_THE_BUS": 0.55, "DEFENSIVE": 0.80, "BALANCED": 1.00, "ATTACKING": 1.25}


def test_equal_profiles_and_mentalities_split_initiative_evenly():
    p = _profile()
    assert svc.initiative_probability(p, "BALANCED", p, "BALANCED") == 0.5


def test_attacking_mentality_wins_more_initiative_than_park_the_bus_at_equal_midfield():
    p = _profile()
    prob = svc.initiative_probability(p, "ATTACKING", p, "PARK_THE_BUS")
    assert prob > 0.5


def test_stronger_midfield_wins_more_initiative_at_equal_mentality():
    strong = _profile(midfield_control=90)
    weak = _profile(midfield_control=50)
    prob = svc.initiative_probability(strong, "BALANCED", weak, "BALANCED")
    assert prob > 0.5


import random as _random
from dataclasses import dataclass

from app.models.enums import Position


@dataclass
class _FakePlayer:
    position: Position
    rating: int
    display_name: str = "Test Player"  # _card_to_actor (Task 9) reads this


@dataclass
class _FakeCard:
    id: int
    player: _FakePlayer
    player_id: int = 0  # _card_to_actor (Task 9) reads this


def test_weighted_pick_only_returns_eligible_positions_for_the_zone():
    cards = [
        _FakeCard(1, _FakePlayer(Position.ST, 90)),
        _FakeCard(2, _FakePlayer(Position.CB, 90)),
    ]
    for _ in range(20):
        picked = svc.weighted_pick(cards, "central_attack")
        assert picked.id == 1  # only the ST has any central_attack weight


def test_weighted_pick_respects_exclude_ids():
    cards = [
        _FakeCard(1, _FakePlayer(Position.ST, 90)),
        _FakeCard(2, _FakePlayer(Position.LW, 90)),
    ]
    for _ in range(20):
        picked = svc.weighted_pick(cards, "central_attack", exclude_ids=frozenset({1}))
        assert picked.id == 2


def test_zone_ratio_favors_the_higher_effective_rating():
    # zone_ratio is a plain rating-share formula (eff_a/(eff_a+eff_b)), not
    # squared or sigmoid-shaped, so even the widest possible rating gap at
    # position_fit==1.0 on both sides (99 vs 58) only reaches ~0.63 — well
    # short of 0.75. STAGE1_BANDS'/STAGE2_BANDS' ">0.75" tier is reachable
    # only through the counter-attack chain's extra multipliers (Task 8's
    # transition_bonus/first_pass_quality_factor), not a plain Stage-1/
    # Stage-2 duel — a real, intentional structural property of the design,
    # not a bug. This test checks the achievable direction/magnitude for a
    # 94-vs-65 matchup: 94/(94+65)=0.591.
    strong = _FakeCard(1, _FakePlayer(Position.ST, 94))
    weak = _FakeCard(2, _FakePlayer(Position.CB, 65))
    ratio = svc.zone_ratio(strong, "central_attack", weak, "central_defence")
    assert ratio > 0.55


def test_zone_ratio_is_half_for_identical_effective_ratings():
    a = _FakeCard(1, _FakePlayer(Position.ST, 80))
    b = _FakeCard(2, _FakePlayer(Position.ST, 80))
    assert svc.zone_ratio(a, "central_attack", b, "central_attack") == 0.5


def test_resolve_stage1_weights_advance_more_at_high_ratio(monkeypatch):
    captured = {}
    def fake_choices(population, weights=None, k=1):
        captured["weights"] = weights
        return [population[-1]]
    monkeypatch.setattr(svc.random, "choices", fake_choices)
    svc.resolve_stage1(0.90)
    assert captured["weights"] == [0.10, 0.25, 0.65]
    svc.resolve_stage1(0.30)
    assert captured["weights"] == [0.45, 0.35, 0.20]


def test_resolve_quality_weights_very_high_more_at_strong_advantage(monkeypatch):
    captured = {}
    def fake_choices(population, weights=None, k=1):
        captured["weights"] = weights
        return [population[0]]
    monkeypatch.setattr(svc.random, "choices", fake_choices)
    svc.resolve_quality(0.80)
    assert captured["weights"] == [0.05, 0.20, 0.50, 0.25]
    svc.resolve_quality(0.20)
    assert captured["weights"] == [0.55, 0.35, 0.09, 0.01]


def _back_line(n: int, start_id: int = 1) -> list[_FakeCard]:
    return [_FakeCard(start_id + i, _FakePlayer(Position.CB, 70)) for i in range(n)]


def test_park_the_bus_keeps_the_full_back_line_eligible():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "PARK_THE_BUS", "CENTRAL_PLAY")
    assert len(pool) == 4


def test_attacking_shrinks_the_pool_below_the_full_back_line():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    assert len(pool) < 4
    assert len(pool) >= 1


def test_high_press_shrinks_the_pool_further_than_the_same_mentality_without_it():
    cards = _back_line(10)
    without_press = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    with_press = svc.defensive_pool(cards, "ATTACKING", "HIGH_PRESS")
    assert len(with_press) <= len(without_press)


def test_defensive_pool_never_drops_below_one():
    cards = _back_line(1)
    pool = svc.defensive_pool(cards, "ATTACKING", "HIGH_PRESS")
    assert len(pool) == 1


def test_defensive_pool_is_drawn_from_real_unmodified_ratings():
    cards = _back_line(4)
    pool = svc.defensive_pool(cards, "ATTACKING", "CENTRAL_PLAY")
    for card in pool:
        assert card.player.rating == 70  # never adjusted, per spec §6.4
        assert card in cards


from app.services.club_tactical_profile_service import TeamTacticalProfile as _TTP


def _side(cards, mentality="BALANCED", playstyle="CENTRAL_PLAY", midfield_control=70) -> "svc.ClubTacticalSide":
    profile = _TTP(central_attack=70, wing_attack=70, midfield_control=midfield_control, central_defence=70, wing_defence=70, goalkeeping=70, team_strength=700)
    return svc.ClubTacticalSide(cards=cards, profile=profile, mentality=mentality, playstyle=playstyle)


def test_first_pass_quality_factor_increases_with_midfield_control():
    assert svc._first_pass_quality_factor(90) > svc._first_pass_quality_factor(60)


def test_resolve_counter_strongly_favors_elite_attacker_against_weak_bus_defence():
    elite_forwards = [
        _FakeCard(1, _FakePlayer(Position.ST, 95)), _FakeCard(2, _FakePlayer(Position.LW, 93)), _FakeCard(3, _FakePlayer(Position.RW, 94)),
        _FakeCard(4, _FakePlayer(Position.CM, 80)),
    ]
    weak_defenders = [_FakeCard(10 + i, _FakePlayer(Position.CB, 65)) for i in range(4)]

    y = _side(elite_forwards, mentality="ATTACKING", playstyle="COUNTER_ATTACK")  # Y just won the ball, now counters
    x = _side(weak_defenders, mentality="PARK_THE_BUS", playstyle="BALANCED")     # X is the bus side conceding the counter

    # A ~95-rated forward (boosted by COUNTER_ATTACK's 1.5x transition bonus)
    # against a genuinely 65-rated defender lands the duel's zone_ratio around
    # 0.6-0.65 — comfortably in STAGE1_BANDS' "0.60-0.75" bucket, not the top
    # ">0.75" one, since the defender's rating is never reduced (spec §6.5's
    # whole point: PARK_THE_BUS keeps the full pool eligible, but every
    # member of it stays genuinely weak). Assert on the duel's own ratio and,
    # among transitions that actually advance, the quality skew — not a flat
    # "most of all trials are high quality", since many phases legitimately
    # stall or get won back before any shot chance exists at all.
    trials = 300
    ratios = []
    advanced = 0
    high_or_very_high = 0
    for _ in range(trials):
        outcome = svc.resolve_counter("a", y, x)
        if outcome is not None:
            advanced += 1
            quality, ratio = outcome
            ratios.append(ratio)
            if quality in ("HIGH", "VERY_HIGH", "CLEAN_BREAKAWAY"):
                high_or_very_high += 1

    assert advanced > 0
    assert sum(ratios) / len(ratios) > 0.55  # the duel itself consistently favors Y's elite forwards
    assert high_or_very_high / advanced > 0.40  # among successful transitions, quality skews toward HIGH/VERY_HIGH


def test_resolve_counter_returns_none_on_a_stalled_or_re_broken_transition(monkeypatch):
    monkeypatch.setattr(svc, "resolve_stage1", lambda ratio: "stall")
    y = _side([_FakeCard(1, _FakePlayer(Position.ST, 80))])
    x = _side([_FakeCard(2, _FakePlayer(Position.CB, 80))])
    assert svc.resolve_counter("a", y, x) is None
