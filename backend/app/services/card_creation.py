from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
    player = await db.get(Player, player_id)
    # Refresh only next_serial_number under a row lock. Callers (e.g.
    # pack_service.pick_random_player) typically already loaded this same
    # Player earlier in the request, so without a forced refresh the
    # increment below could silently read a stale value. Scoping
    # attribute_names to just this column (instead of a full
    # populate_existing re-select) avoids two problems a broader refresh
    # would reintroduce: Postgres rejects FOR UPDATE against the nullable
    # side of the mapper's default LEFT JOIN on `collection`, and a full
    # re-populate would reset `collection` back to "not loaded" on this
    # object even when a caller already eager-loaded it — which crashed
    # response serialization with a sync lazy-load (MissingGreenlet) for
    # any player that belongs to a card collection.
    await db.refresh(player, attribute_names=["next_serial_number"], with_for_update=True)
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
