from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding


def apply_match_result(
    standing_a: TournamentClubStanding, standing_b: TournamentClubStanding, score_a: int, score_b: int
) -> None:
    standing_a.goals_for += score_a
    standing_a.goals_against += score_b
    standing_b.goals_for += score_b
    standing_b.goals_against += score_a
    if score_a > score_b:
        standing_a.points += 3
    elif score_b > score_a:
        standing_b.points += 3
    else:
        standing_a.points += 1
        standing_b.points += 1


def _head_to_head_points(club_ids: set[int], matches: list[TournamentMatch]) -> dict[int, int]:
    points: dict[int, int] = {club_id: 0 for club_id in club_ids}
    for m in matches:
        if m.club_a_id not in club_ids or m.club_b_id not in club_ids:
            continue
        if m.score_a > m.score_b:
            points[m.club_a_id] += 3
        elif m.score_b > m.score_a:
            points[m.club_b_id] += 3
        else:
            points[m.club_a_id] += 1
            points[m.club_b_id] += 1
    return points


def rank_standings(standings: list[TournamentClubStanding], matches: list[TournamentMatch]) -> list[TournamentClubStanding]:
    """Sort: points desc, goal difference desc, goals for desc, then
    head-to-head points (computed only among clubs still tied after the
    first three keys) desc. A true unbreakable N-way cycle falls back to
    stable input order — there is nothing left to sort by at that point."""
    def gd(s: TournamentClubStanding) -> int:
        return s.goals_for - s.goals_against

    groups: dict[tuple[int, int, int], list[TournamentClubStanding]] = {}
    for s in standings:
        key = (s.points, gd(s), s.goals_for)
        groups.setdefault(key, []).append(s)

    ranked: list[TournamentClubStanding] = []
    for key in sorted(groups.keys(), reverse=True):
        group = groups[key]
        if len(group) == 1:
            ranked.extend(group)
            continue
        h2h = _head_to_head_points({s.club_id for s in group}, matches)
        ranked.extend(sorted(group, key=lambda s: h2h[s.club_id], reverse=True))
    return ranked
