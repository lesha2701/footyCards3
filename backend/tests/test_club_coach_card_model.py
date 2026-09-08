import pytest
import pytest_asyncio

from app.models.club import Club
from app.models.coach import Coach, CoachBoost
from app.models.enums import ClubCoachCardSource, ClubLogoShape, ClubType, CoachBoostType, Rarity
from app.models.user import User


@pytest_asyncio.fixture
async def seed_club(db_session):
    """Create a User and Club for testing."""
    user = User(telegram_id=999_000_123, username="test_user")
    db_session.add(user)
    await db_session.flush()

    club = Club(
        name="Test Club",
        club_type=ClubType.open,
        logo_shape=ClubLogoShape.shield,
        logo_color="#FF0000",
        captain_id=user.id,
        invite_code="testcl123",
    )
    db_session.add(club)
    await db_session.flush()
    await db_session.refresh(club)
    return club


async def test_club_coach_card_persists_and_loads_coach_joined(db_session, seed_club):
    from app.models.club_coach_card import ClubCoachCard

    coach = Coach(display_name="Test Coach", rarity=Rarity.rare)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=4.0)]
    db_session.add(coach)
    await db_session.flush()

    card = ClubCoachCard(
        club_id=seed_club.id,
        coach_id=coach.id,
        serial_number=1,
        source=ClubCoachCardSource.club_pack,
    )
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)

    assert card.id is not None
    assert card.coach.display_name == "Test Coach"
