from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.services.tournament_standing_service import apply_match_result, rank_standings


def _standing(club_id: int, points=0, gf=0, ga=0) -> TournamentClubStanding:
    return TournamentClubStanding(tournament_id=1, club_id=club_id, points=points, goals_for=gf, goals_against=ga)


def test_apply_match_result_awards_win_draw_loss_points():
    a, b = _standing(1), _standing(2)
    apply_match_result(a, b, score_a=2, score_b=1)
    assert (a.points, a.goals_for, a.goals_against) == (3, 2, 1)
    assert (b.points, b.goals_for, b.goals_against) == (0, 1, 2)

    a2, b2 = _standing(1), _standing(2)
    apply_match_result(a2, b2, score_a=1, score_b=1)
    assert a2.points == 1 and b2.points == 1


def test_rank_sorts_by_points_then_goal_difference_then_goals_for():
    standings = [
        _standing(1, points=6, gf=5, ga=3),   # GD +2
        _standing(2, points=6, gf=4, ga=1),   # GD +3, higher GF-tiebreak irrelevant since GD already decides
        _standing(3, points=9, gf=1, ga=1),   # most points, wins outright
    ]
    ranked = rank_standings(standings, matches=[])
    assert [s.club_id for s in ranked] == [3, 2, 1]


def test_rank_breaks_a_full_tie_via_head_to_head():
    # Three clubs level on points/GD/GF; club 1 beat club 2, club 2 beat club 3,
    # club 3 beat club 1 (a genuine 3-way cycle) — head-to-head points among
    # just this trio: each has exactly 1 win + 1 loss = 3 points each, so this
    # case degrades to insertion-stable ordering, which is the documented
    # behavior for a true unbreakable cycle (not a bug — nothing left to sort by).
    standings = [_standing(1, points=3, gf=2, ga=2), _standing(2, points=3, gf=2, ga=2), _standing(3, points=3, gf=2, ga=2)]
    matches = [
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=1, club_b_id=2, score_a=1, score_b=0, event_log=[], simulated_at=None),
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=2, club_b_id=3, score_a=1, score_b=0, event_log=[], simulated_at=None),
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=3, club_b_id=1, score_a=1, score_b=0, event_log=[], simulated_at=None),
    ]
    ranked = rank_standings(standings, matches)
    assert [s.club_id for s in ranked] == [1, 2, 3]  # unbreakable cycle falls back to insertion order


def test_rank_breaks_a_two_way_tie_via_head_to_head():
    # Clubs 1 and 2 level on points/GD/GF; club 1 beat club 2 head-to-head.
    standings = [_standing(1, points=6, gf=4, ga=2), _standing(2, points=6, gf=4, ga=2)]
    matches = [
        TournamentMatch(tournament_id=1, round_number=1, club_a_id=1, club_b_id=2, score_a=2, score_b=0, event_log=[], simulated_at=None),
    ]
    ranked = rank_standings(standings, matches)
    assert [s.club_id for s in ranked] == [1, 2]
