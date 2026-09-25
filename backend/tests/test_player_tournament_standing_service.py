from types import SimpleNamespace as NS

from app.services.player_tournament_standing_service import apply_match_result, rank_standings


def _standing(user_id, points=0, gf=0, ga=0):
    return NS(user_id=user_id, points=points, goals_for=gf, goals_against=ga)


def _match(a, b, sa, sb):
    return NS(user_a_id=a, user_b_id=b, score_a=sa, score_b=sb)


def test_apply_win_draw():
    a, b = _standing(1), _standing(2)
    apply_match_result(a, b, 2, 1)
    assert (a.points, a.goals_for, a.goals_against) == (3, 2, 1)
    assert (b.points, b.goals_for, b.goals_against) == (0, 1, 2)
    apply_match_result(a, b, 1, 1)
    assert (a.points, b.points) == (4, 1)


def test_rank_by_points_then_goal_difference():
    s = [_standing(1, 6, 5, 5), _standing(2, 6, 7, 3), _standing(3, 9, 1, 1)]
    assert [x.user_id for x in rank_standings(s, [])] == [3, 2, 1]


def test_rank_head_to_head_breaks_full_tie():
    s = [_standing(1, 3, 2, 1), _standing(2, 3, 2, 1)]
    matches = [_match(1, 2, 0, 1)]
    assert [x.user_id for x in rank_standings(s, matches)] == [2, 1]
