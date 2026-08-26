from sqlalchemy import select

from app.models.club_card import ClubCard
from app.models.enums import ClubCardSource
from app.services.club_card_service import create_club_card
from tests.factories import create_player


async def test_create_club_card_uses_separate_serial_sequence_from_personal_cards(db_session):
    player = await create_player(db_session)
    assert player.next_serial_number == 1
    assert player.next_club_serial_number == 1

    club_card_1 = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.starter_seed)
    club_card_2 = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.starter_seed)
    await db_session.commit()

    assert club_card_1.serial_number == 1
    assert club_card_2.serial_number == 2
    await db_session.refresh(player)
    assert player.next_serial_number == 1  # untouched — personal-card sequence is independent
    assert player.next_club_serial_number == 3


async def test_create_club_card_persists_with_player_relationship(db_session):
    player = await create_player(db_session)
    card = await create_club_card(db_session, club_id=1, player_id=player.id, source=ClubCardSource.club_pack, source_ref_id=42)
    await db_session.commit()

    result = await db_session.execute(select(ClubCard).where(ClubCard.id == card.id))
    fetched = result.scalar_one()
    assert fetched.player.id == player.id
    assert fetched.source == ClubCardSource.club_pack
    assert fetched.source_ref_id == 42
