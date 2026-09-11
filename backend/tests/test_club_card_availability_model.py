from sqlalchemy.exc import IntegrityError

from app.models.club_card_availability import ClubCardAvailability
from app.models.enums import ClubCardAvailabilityReason


async def test_availability_unique_per_card(db_session):
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=2, reason=ClubCardAvailabilityReason.red_card))
    await db_session.flush()
    db_session.add(ClubCardAvailability(club_card_id=1, rounds_remaining=1, reason=ClubCardAvailabilityReason.red_card))
    try:
        await db_session.flush()
        assert False, "expected IntegrityError"
    except IntegrityError:
        await db_session.rollback()
