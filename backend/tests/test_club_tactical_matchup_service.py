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
