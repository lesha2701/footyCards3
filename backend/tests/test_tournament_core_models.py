from app.models.enums import TournamentStatus
from app.models.tournament import Tournament, TournamentClub


async def test_tournament_defaults(db_session):
    t = Tournament()
    db_session.add(t)
    await db_session.commit()
    await db_session.refresh(t)
    assert t.status == TournamentStatus.active
    assert t.rounds_simulated == 0


async def test_tournament_club_unique_per_pair(db_session):
    from sqlalchemy.exc import IntegrityError
    t = Tournament()
    db_session.add(t)
    await db_session.flush()
    db_session.add(TournamentClub(tournament_id=t.id, club_id=1))
    await db_session.flush()
    db_session.add(TournamentClub(tournament_id=t.id, club_id=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()
