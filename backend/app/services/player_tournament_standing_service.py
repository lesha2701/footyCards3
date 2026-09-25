from app.models.player_tournament import PlayerTournamentMatch, PlayerTournamentStanding


def apply_match_result(
    standing_a: PlayerTournamentStanding, standing_b: PlayerTournamentStanding, score_a: int, score_b: int
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


def _head_to_head_points(user_ids: set[int], matches: list[PlayerTournamentMatch]) -> dict[int, int]:
    points = {user_id: 0 for user_id in user_ids}
    for m in matches:
        if m.user_a_id not in user_ids or m.user_b_id not in user_ids:
            continue
        if m.score_a > m.score_b:
            points[m.user_a_id] += 3
        elif m.score_b > m.score_a:
            points[m.user_b_id] += 3
        else:
            points[m.user_a_id] += 1
            points[m.user_b_id] += 1
    return points


def rank_standings(
    standings: list[PlayerTournamentStanding], matches: list[PlayerTournamentMatch]
) -> list[PlayerTournamentStanding]:
    """Same ordering rules as tournament_standing_service.rank_standings
    (clubs): points, goal difference, goals for, then head-to-head points
    computed only among players still tied. An unbreakable cycle keeps the
    stable input order."""
    groups: dict[tuple[int, int, int], list[PlayerTournamentStanding]] = {}
    for s in standings:
        groups.setdefault((s.points, s.goals_for - s.goals_against, s.goals_for), []).append(s)

    ranked: list[PlayerTournamentStanding] = []
    for key in sorted(groups.keys(), reverse=True):
        group = groups[key]
        if len(group) == 1:
            ranked.extend(group)
            continue
        h2h = _head_to_head_points({s.user_id for s in group}, matches)
        ranked.extend(sorted(group, key=lambda s: h2h[s.user_id], reverse=True))
    return ranked
