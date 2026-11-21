import asyncio
import logging
from typing import Optional

from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm.attributes import set_committed_value

from app.core.exceptions import ConflictError
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.enums import CardSource
from app.models.player import Player
from app.models.stadium import Stadium
from app.models.user_coach_card import UserCoachCard
from app.models.user_stadium_card import UserStadiumCard

logger = logging.getLogger(__name__)

# Serial numbers of unlimited cards come from a short transaction of their
# own: in the caller's transaction the Player row stayed locked until the
# whole pack opening committed, and newcomers' packs draw from one small pool
# — a wave of them queued for seconds on the same rows. A rolled-back
# opening leaves a gap in the numbers, which is fine for an unlimited card;
# a numbered edition (edition_size) keeps the old locked path, its numbers
# are a promise. Own small pool per database, so it never waits on the
# request pool it is called from.
_serial_engines: dict[str, AsyncEngine] = {}


def _serial_engine(db: AsyncSession) -> Optional[AsyncEngine]:
    bind = db.bind
    if not isinstance(bind, AsyncEngine) or bind.dialect.name != "postgresql":
        return None
    # Per event loop too: asyncpg connections can't cross loops (tests run one each).
    key = f"{id(asyncio.get_running_loop())}:{bind.url.render_as_string(hide_password=False)}"
    if key not in _serial_engines:
        _serial_engines[key] = create_async_engine(
            bind.url, pool_size=2, max_overflow=3, pool_timeout=5, pool_pre_ping=True,
        )
    return _serial_engines[key]


async def _take_serial_now(db: AsyncSession, player_id: int) -> Optional[int]:
    """The next serial of `player_id`, committed at once — or None when it
    can't be had quickly (the caller's own transaction may hold the row:
    waiting would hang it), and the caller takes it the locked way."""
    engine = _serial_engine(db)
    if engine is None:
        return None
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL lock_timeout = '2s'"))
            return await conn.scalar(
                update(Player).where(Player.id == player_id)
                .values(next_serial_number=Player.next_serial_number + 1)
                .returning(Player.next_serial_number - 1)
            )
    except (DBAPIError, TimeoutError, OSError):
        logger.warning("quick serial for player %s failed, taking it under the row lock", player_id, exc_info=True)
        return None


async def create_user_card(
    db: AsyncSession, owner_id: int, player_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserCard:
    """Creates a card instance with a per-player serial number: the first
    ever copy of a given Player gets #1, the second gets #2, etc.,
    independently of other players. An unlimited card takes its number in a
    short transaction of its own (_take_serial_now); a numbered edition —
    or when that fails — locks the Player row for the caller's transaction
    to read-and-increment its counter."""
    player = await db.get(Player, player_id)
    if player.edition_size is None:
        serial_number = await _take_serial_now(db, player_id)
        if serial_number is not None:
            # In step with the row, without making the player dirty here.
            set_committed_value(player, "next_serial_number", serial_number + 1)
            return await _new_card(db, owner_id, player_id, source, source_ref_id, serial_number)
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
    # A numbered edition is a promise: only a paid order (never refused) may
    # pass it — see card_offer_service.reserve_for_invoice.
    if player.edition_size is not None and serial_number > player.edition_size and source != CardSource.stars_purchase:
        raise ConflictError(f"Тираж карты {player.display_name} закончился")
    player.next_serial_number += 1
    db.add(player)
    return await _new_card(db, owner_id, player_id, source, source_ref_id, serial_number)


async def _new_card(
    db: AsyncSession, owner_id: int, player_id: int, source: CardSource, source_ref_id: Optional[int], serial_number: int,
) -> UserCard:
    from app.services.card_value_service import bound_at_creation

    card = UserCard(
        owner_id=owner_id, player_id=player_id, source=source, source_ref_id=source_ref_id,
        serial_number=serial_number, from_free_source=await bound_at_creation(db, source, source_ref_id),
    )
    db.add(card)
    await db.flush()
    from app.services.artifact_service import apply_card_bonus
    from app.services.trade_finder_service import notify_wanted_card

    await apply_card_bonus(db, card)
    await notify_wanted_card(db, owner_id, player_id)
    return card


async def create_user_coach_card(
    db: AsyncSession, owner_id: int, coach_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserCoachCard:
    """Mirrors create_user_card exactly, but against Coach.next_serial_number
    (the personal-ownership counter — distinct from next_club_serial_number,
    which club coach acquisitions use) — personal coach acquisitions must
    never affect club-side serial-number scarcity, and the counter must be
    read-and-incremented under a row lock rather than a racy
    MAX(serial_number) + 1 scan, matching every other serial-number
    allocation in this codebase."""
    coach = await db.get(Coach, coach_id)
    await db.refresh(coach, attribute_names=["next_serial_number"], with_for_update=True)
    serial_number = coach.next_serial_number
    coach.next_serial_number += 1
    db.add(coach)

    card = UserCoachCard(user_id=owner_id, coach_id=coach_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number)
    db.add(card)
    await db.flush()
    return card


async def create_user_stadium_card(
    db: AsyncSession, owner_id: int, stadium_id: int, source: CardSource, source_ref_id: Optional[int] = None
) -> UserStadiumCard:
    """Mirrors create_user_coach_card exactly, but against
    Stadium.next_serial_number (the personal-ownership counter — distinct
    from next_club_serial_number, which club stadium acquisitions use) —
    personal stadium acquisitions must never affect club-side serial-number
    scarcity, and the counter must be read-and-incremented under a row lock
    rather than a racy MAX(serial_number) + 1 scan, matching every other
    serial-number allocation in this codebase."""
    stadium = await db.get(Stadium, stadium_id)
    await db.refresh(stadium, attribute_names=["next_serial_number"], with_for_update=True)
    serial_number = stadium.next_serial_number
    stadium.next_serial_number += 1
    db.add(stadium)

    card = UserStadiumCard(
        user_id=owner_id, stadium_id=stadium_id, source=source, source_ref_id=source_ref_id, serial_number=serial_number,
    )
    db.add(card)
    await db.flush()
    return card
