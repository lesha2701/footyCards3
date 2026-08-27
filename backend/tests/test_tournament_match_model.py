from datetime import datetime, timezone

from app.models.tournament import Tournament
from app.models.tournament_match import TournamentMatch


async def test_tournament_match_stores_event_log_json(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    m = TournamentMatch(
        tournament_id=t.id, round_number=1, club_a_id=1, club_b_id=2,
        score_a=2, score_b=1, event_log=[{"minute": 5, "event_type": "goal", "team": "a"}],
        simulated_at=datetime.now(timezone.utc),
    )
    db_session.add(m)
    await db_session.commit()
    await db_session.refresh(m)
    assert m.event_log[0]["event_type"] == "goal"
