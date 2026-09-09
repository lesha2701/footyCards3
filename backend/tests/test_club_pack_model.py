import pytest
from sqlalchemy.exc import IntegrityError

from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.club_coach_card import ClubCoachCard
from app.models.club_pack import ClubPack
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.coach import Coach
from app.models.enums import ClubCardSource, ClubCoachCardSource, ClubLogoShape, ClubType, Rarity
from app.models.user import User
from tests.factories import create_player


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

    # Both FKs set — must also be rejected. Needs real referenced rows (not just any
    # int) so the failure is actually the `ck_club_pack_opening_card_exactly_one_kind`
    # CHECK constraint firing, not an unrelated FK violation.
    player = await create_player(db_session)
    club_card = ClubCard(club_id=club.id, player_id=player.id, serial_number=1, source=ClubCardSource.club_pack)
    db_session.add(club_card)
    coach = Coach(display_name="Both-FK Test Coach", rarity=Rarity.common, is_active=True, is_pack_droppable=True)
    db_session.add(coach)
    await db_session.flush()
    club_coach_card = ClubCoachCard(club_id=club.id, coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(club_coach_card)
    await db_session.flush()

    db_session.add(
        ClubPackOpeningCard(opening_id=opening.id, club_card_id=club_card.id, club_coach_card_id=club_coach_card.id, is_new=True)
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
