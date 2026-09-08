import pytest_asyncio

from app.models.club import Club
from app.models.club_coach_card import ClubCoachCard
from app.models.club_coach_pack import ClubCoachPack, ClubCoachPackRarityProbability
from app.models.club_coach_pack_opening import ClubCoachPackOpening, ClubCoachPackOpeningCard
from app.models.coach import Coach
from app.models.enums import ClubCoachCardSource, ClubLogoShape, ClubType, Rarity
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


@pytest_asyncio.fixture
async def seed_user(db_session):
    """Create a second User (the pack opener) for testing."""
    user = User(telegram_id=999_000_456, username="opener_user")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def test_club_coach_pack_with_probabilities_persists(db_session):
    pack = ClubCoachPack(slug="test-coach-pack", name="Test Coach Pack", price=100, card_count=1)
    pack.rarity_probabilities = [ClubCoachPackRarityProbability(rarity=Rarity.common, probability=1.0)]
    db_session.add(pack)
    await db_session.commit()

    # Not db_session.refresh(pack): with expire_on_commit=False (this test
    # suite's session config, see conftest.py), the relationship set above
    # stays populated in memory across commit — refreshing here would expire
    # it and trigger an async lazy-load outside a greenlet context
    # (SQLAlchemy's MissingGreenlet), since the relationship isn't eager
    # (unlike ClubCoachCard.coach's lazy="joined").
    assert pack.id is not None
    assert len(pack.rarity_probabilities) == 1


async def test_club_coach_pack_opening_links_cards(db_session, seed_club, seed_user):
    coach = Coach(display_name="Opened Coach", rarity=Rarity.common)
    db_session.add(coach)
    await db_session.flush()
    card = ClubCoachCard(club_id=seed_club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    pack = ClubCoachPack(slug="opening-test-pack", name="Opening Test Pack", price=50, card_count=1)
    db_session.add(pack)
    await db_session.flush()

    opening = ClubCoachPackOpening(club_id=seed_club.id, club_coach_pack_id=pack.id, opened_by_user_id=seed_user.id, price_paid=50)
    opening.cards = [ClubCoachPackOpeningCard(club_coach_card_id=card.id, is_new_coach=True)]
    db_session.add(opening)
    await db_session.commit()

    # See the note in the test above: no db_session.refresh(opening) here,
    # for the same reason (would expire the non-eager `cards` relationship).
    assert len(opening.cards) == 1
