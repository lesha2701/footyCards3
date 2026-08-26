from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.club_card import ClubCard
from app.models.enums import ClubCardSource
from app.models.player import Player


async def create_club_card(
    db: AsyncSession, club_id: int, player_id: int, source: ClubCardSource, source_ref_id: Optional[int] = None
) -> ClubCard:
    """Mirrors card_creation.create_user_card exactly, but against the
    separate `next_club_serial_number` counter — club packs must never
    affect personal-card serial-number scarcity."""
    player = await db.get(Player, player_id)
    await db.refresh(player, attribute_names=["next_club_serial_number"], with_for_update=True)
    serial_number = player.next_club_serial_number
    player.next_club_serial_number += 1
    db.add(player)

    card = ClubCard(club_id=club_id, player_id=player_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card
