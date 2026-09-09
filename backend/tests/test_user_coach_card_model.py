import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import Pool

from app.models.coach import Coach, CoachBoost
from app.models.enums import CardSource, CoachBoostType, Rarity
from app.models.user import User
from app.models.user_coach_card import UserCoachCard


# Enable foreign key constraints for SQLite
@event.listens_for(Pool, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def test_user_coach_card_requires_a_real_coach_and_user(db_session):
    user = User(telegram_id=999_200_100, username="coach_card_test_user")
    db_session.add(user)
    coach = Coach(display_name="Personal Test Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()

    card = UserCoachCard(user_id=user.id, coach_id=coach.id, serial_number=1, source=CardSource.pack)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)

    assert card.id is not None
    assert card.acquired_at is not None


async def test_user_coach_card_rejects_a_nonexistent_coach(db_session):
    user = User(telegram_id=999_200_101, username="coach_card_test_user_2")
    db_session.add(user)
    await db_session.flush()

    card = UserCoachCard(user_id=user.id, coach_id=999_999, serial_number=1, source=CardSource.pack)
    db_session.add(card)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
