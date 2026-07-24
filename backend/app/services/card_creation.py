from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.models.card import UserCard
from app.models.enums import CardSource
from app.models.player import Player


async def create_user_card(
    db: AsyncSession, owner_id: int, player_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserCard:
    """Creates a card instance with a per-player serial number: the first
    ever copy of a given Player gets #1, the second gets #2, etc.,
    independently of other players. The Player row is locked for the
    duration to atomically read-and-increment its counter."""
    # lazyload overrides the model's default lazy="joined" on `collection` —
    # Postgres rejects FOR UPDATE against the nullable side of a LEFT JOIN.
    # populate_existing is required because callers (e.g. pack_service via
    # pick_random_player) typically already loaded this same Player earlier
    # in the request; without it, SQLAlchemy's identity map would return
    # that stale pre-lock object instead of the freshly locked row, so the
    # increment below could silently read a stale next_serial_number.
    query = (
        select(Player)
        .where(Player.id == player_id)
        .options(lazyload(Player.collection))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    player = (await db.execute(query)).scalar_one()
    serial_number = player.next_serial_number
    player.next_serial_number += 1
    db.add(player)

    card = UserCard(
        owner_id=owner_id, player_id=player_id, source=source, source_ref_id=source_ref_id,
        serial_number=serial_number,
    )
    db.add(card)
    await db.flush()
    return card
