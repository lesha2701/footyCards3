import pytest
from sqlalchemy.exc import IntegrityError

from app.models.club import Club
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.enums import ClubLogoShape, ClubType
from app.models.user import User


@pytest.mark.asyncio
async def test_club_pack_coach_drop_chance_defaults_to_zero(db_session):
    pack = ClubPack(slug="test-pack-default", name="Test Pack", price=100, card_count=3)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    assert pack.coach_drop_chance == 0.0


@pytest.mark.asyncio
async def test_club_pack_opening_card_rejects_both_or_neither_fk_set(db_session):
    user = User(telegram_id=999_100_900, username="pack_slot_test_user")
    db_session.add(user)
    await db_session.flush()
    club = Club(name="Slot Test Club", club_type=ClubType.open, logo_shape=ClubLogoShape.shield, logo_color="#FF0000", captain_id=user.id, invite_code="testcode123")
    db_session.add(club)
    await db_session.flush()
    pack = ClubPack(slug="test-pack-slot", name="Test Pack", price=100, card_count=1)
    db_session.add(pack)
    await db_session.flush()
    opening = ClubPackOpening(club_id=club.id, club_pack_id=pack.id, opened_by_user_id=user.id, price_paid=100)
    db_session.add(opening)
    await db_session.flush()

    # Neither FK set — must be rejected.
    db_session.add(ClubPackOpeningCard(opening_id=opening.id, club_card_id=None, club_coach_card_id=None, is_new=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
