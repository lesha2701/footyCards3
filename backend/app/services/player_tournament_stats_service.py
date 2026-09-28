from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player_tournament import PlayerTournamentMatch
from app.models.user import User
from app.schemas.player_tournament_stats import PlayerTournamentStatsOut


async def get_player_tournament_stats(db: AsyncSession, user: User) -> PlayerTournamentStatsOut:
    """All-time record across every personal tournament the player has ever played — not
    scoped to the current tournament. Mirrors club_stats_service.get_club_stats exactly,
    swapping club_id for user_id and the club match columns for the player ones."""
    matches = (
        await db.execute(
            select(
                PlayerTournamentMatch.user_a_id, PlayerTournamentMatch.user_b_id,
                PlayerTournamentMatch.score_a, PlayerTournamentMatch.score_b,
            )
            .where((PlayerTournamentMatch.user_a_id == user.id) | (PlayerTournamentMatch.user_b_id == user.id))
        )
    ).all()

    wins = draws = losses = goals_scored = goals_conceded = 0
    for user_a_id, _user_b_id, score_a, score_b in matches:
        own_score, opp_score = (score_a, score_b) if user_a_id == user.id else (score_b, score_a)
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
        return PlayerTournamentStatsOut(
            matches_played=0, wins=0, draws=0, losses=0, goals_scored=0, goals_conceded=0,
            win_rate_pct=0.0, draw_rate_pct=0.0, loss_rate_pct=0.0,
            goals_scored_per_match=0.0, goals_conceded_per_match=0.0,
        )
    return PlayerTournamentStatsOut(
        matches_played=matches_played, wins=wins, draws=draws, losses=losses,
        goals_scored=goals_scored, goals_conceded=goals_conceded,
        win_rate_pct=round(100 * wins / matches_played, 1),
        draw_rate_pct=round(100 * draws / matches_played, 1),
        loss_rate_pct=round(100 * losses / matches_played, 1),
        goals_scored_per_match=round(goals_scored / matches_played, 2),
        goals_conceded_per_match=round(goals_conceded / matches_played, 2),
    )
