from sqlalchemy.exc import IntegrityError

from app.models.club_card_availability import ClubCardAvailability


async def test_availability_unique_per_card(db_session):
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=2))
    await db_session.flush()
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=1))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()
