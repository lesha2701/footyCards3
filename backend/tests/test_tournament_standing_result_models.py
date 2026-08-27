from sqlalchemy.exc import IntegrityError

from app.models.tournament import Tournament
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_standing import TournamentClubStanding


async def test_standing_unique_per_tournament_club(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    db_session.add(TournamentClubStanding(tournament_id=t.id, club_id=1))
    await db_session.flush()
    db_session.add(TournamentClubStanding(tournament_id=t.id, club_id=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()


async def test_result_stores_final_outcome(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    r = TournamentClubResult(tournament_id=t.id, club_id=1, final_rank=1, budget_awarded=1000, stars_delta=3, cup_awarded=True)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    assert r.cup_awarded is True
