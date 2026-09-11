from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tournament_match import TournamentMatch
from app.models.user import User
from app.schemas.club_stats import ClubStatsOut
from app.services.club_service import _require_membership


async def get_club_stats(db: AsyncSession, user: User) -> ClubStatsOut:
    """All-time record across every tournament the club has ever played — not scoped to
    the current tournament. Any club member can view this (read-only, no privileged data),
    matching the same access level as the existing club activity/leaderboard views."""
    membership = await _require_membership(db, user.id)
    club_id = membership.club_id

    matches = (
        await db.execute(
            select(TournamentMatch.club_a_id, TournamentMatch.club_b_id, TournamentMatch.score_a, TournamentMatch.score_b)
            .where((TournamentMatch.club_a_id == club_id) | (TournamentMatch.club_b_id == club_id))
        )
    ).all()

    wins = draws = losses = goals_scored = goals_conceded = 0
    for club_a_id, club_b_id, score_a, score_b in matches:
        own_score, opp_score = (score_a, score_b) if club_a_id == club_id else (score_b, score_a)
        goals_scored += own_score
        goals_conceded += opp_score
        if own_score > opp_score:
            wins += 1
        elif own_score < opp_score:
            losses += 1
        else:
            draws += 1

    matches_played = len(matches)
    if matches_played == 0:
        return ClubStatsOut(
            matches_played=0, wins=0, draws=0, losses=0, goals_scored=0, goals_conceded=0,
            win_rate_pct=0.0, draw_rate_pct=0.0, loss_rate_pct=0.0,
            goals_scored_per_match=0.0, goals_conceded_per_match=0.0,
        )
    return ClubStatsOut(
        matches_played=matches_played, wins=wins, draws=draws, losses=losses,
        goals_scored=goals_scored, goals_conceded=goals_conceded,
        win_rate_pct=round(100 * wins / matches_played, 1),
        draw_rate_pct=round(100 * draws / matches_played, 1),
        loss_rate_pct=round(100 * losses / matches_played, 1),
        goals_scored_per_match=round(goals_scored / matches_played, 2),
        goals_conceded_per_match=round(goals_conceded / matches_played, 2),
    )
