from datetime import datetime, timezone

from app.models.player_tournament import PlayerTournament, PlayerTournamentMatch
from app.services.player_tournament_stats_service import get_player_tournament_stats
from tests.player_tournament_helpers import make_ready_user


async def _add_match(db_session, tournament_id, round_number, a_id, b_id, score_a, score_b):
    from app.models.player_tournament import PlayerTournamentMatch as M
    db_session.add(M(
        tournament_id=tournament_id, round_number=round_number, user_a_id=a_id, user_b_id=b_id,
        score_a=score_a, score_b=score_b, event_log=[], simulated_at=datetime.now(timezone.utc),
    ))


async def test_stats_aggregate_across_all_tournaments(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890100)
    b = await make_ready_user(client, db_session, bot_token, 890101)
    t1 = PlayerTournament()
    t2 = PlayerTournament()
    db_session.add_all([t1, t2])
    await db_session.flush()
    await _add_match(db_session, t1.id, 1, a.id, b.id, 3, 1)  # win
    await _add_match(db_session, t1.id, 2, b.id, a.id, 2, 2)  # draw
    await _add_match(db_session, t2.id, 1, a.id, b.id, 0, 4)  # loss
    await db_session.commit()

    stats = await get_player_tournament_stats(db_session, a)
    assert stats.matches_played == 3
    assert (stats.wins, stats.draws, stats.losses) == (1, 1, 1)
    assert stats.goals_scored == 3 + 2 + 0
    assert stats.goals_conceded == 1 + 2 + 4
    assert stats.win_rate_pct == round(100 / 3, 1)


async def test_stats_zero_matches(client, db_session, bot_token):
    a = await make_ready_user(client, db_session, bot_token, 890110)
    stats = await get_player_tournament_stats(db_session, a)
    assert stats.matches_played == 0
    assert stats.win_rate_pct == 0.0
