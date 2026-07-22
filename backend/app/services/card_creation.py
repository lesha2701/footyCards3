from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import UserCard
from app.models.enums import CardSource


async def create_user_card(
    db: AsyncSession, owner_id: int, player_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserCard:
    """Creates a card instance and assigns its serial_number from its own
    primary key, which is portable across databases (Postgres/SQLite) unlike
    a DB-level IDENTITY/sequence on a non-PK column."""
    card = UserCard(owner_id=owner_id, player_id=player_id, source=source, source_ref_id=source_ref_id)
    db.add(card)
    await db.flush()
    card.serial_number = card.id
    db.add(card)
    return card
