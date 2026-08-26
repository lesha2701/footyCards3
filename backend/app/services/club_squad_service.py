import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.models.club_card import ClubCard
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.enums import ClubCardSource, Position
from app.models.player import Player
from app.models.user import User
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest, ClubLineupSlotOut
from app.schemas.player import PlayerOut
from app.services.club_card_service import create_club_card
from app.services.lineup_service import CATEGORY_POSITIONS, FORMATION_SLOTS, SLOTS_BY_CODE, calculate_base_strength

# app.services.club_service imports seed_starting_squad from this module at
# module load time, so a module-level `from app.services.club_service import
# _require_manager, _require_membership` here would be a circular import;
# each function below imports them locally instead — same cross-service call
# the brief specifies, just deferred until both modules have finished
# initializing.

# Bench categories seeded alongside the 11 starters — one extra card per
# category, giving every fresh club a small reserve pool from day one (per
# the design spec's "so a club is never caught with nobody to substitute").
BENCH_CATEGORIES = ["GK", "DEF", "MID", "FWD"]


async def _pick_weakest_active_player_id(db: AsyncSession, positions: list[Position], excluded_player_ids: set[int]) -> int:
    query = (
        select(Player.id, Player.rating)
        .where(Player.is_active.is_(True), Player.position.in_(positions))
        .order_by(Player.rating.asc())
        .limit(20)
    )
    if excluded_player_ids:
        query = query.where(Player.id.notin_(excluded_player_ids))
    rows = (await db.execute(query)).all()
    if not rows:
        # Fall back to allowing repeats if the active player pool for this
        # position is smaller than the number of slots needing it (e.g. a
        # freshly-seeded dev database) — a duplicate weak player beats no
        # player at all for a brand-new club's starting squad.
        rows = (
            await db.execute(
                select(Player.id, Player.rating)
                .where(Player.is_active.is_(True), Player.position.in_(positions))
                .order_by(Player.rating.asc())
                .limit(20)
            )
        ).all()
    lowest_rating = rows[0][1]
    lowest_rated_ids = [player_id for player_id, rating in rows if rating == lowest_rating]
    return random.choice(lowest_rated_ids)


async def seed_starting_squad(db: AsyncSession, club_id: int) -> None:
    """Mints the club's first 15 ClubCards (11 starters, placed directly
    into a fresh ClubLineup, plus 4 bench cards — one per category) using
    the lowest-rated active Player available per slot, random among ties.
    Deliberately weak by design — the club has to earn its way up via
    packs. Called once, synchronously, from club_service.create_club."""
    lineup = ClubLineup(club_id=club_id)
    db.add(lineup)
    await db.flush()

    used_player_ids: set[int] = set()

    for slot in FORMATION_SLOTS:
        positions = list(CATEGORY_POSITIONS[slot.category])
        # Position enum members compare by value against Player.position's
        # own enum column — no str() conversion needed, matches how
        # lineup_service itself queries by these same enum members.
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        club_card = await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=club_card.id, slot_code=slot.code))

    for category in BENCH_CATEGORIES:
        positions = list(CATEGORY_POSITIONS[category])
        player_id = await _pick_weakest_active_player_id(db, positions, used_player_ids)
        used_player_ids.add(player_id)
        await create_club_card(db, club_id, player_id, ClubCardSource.starter_seed)
        # No ClubLineupCard row for bench cards — per this plan's "bench =
        # any club card not currently in the lineup" simplification, these
        # are just extra ClubCard rows the squad editor's picker surfaces.

    await db.flush()


async def _get_or_none_lineup(db: AsyncSession, club_id: int) -> ClubLineup | None:
    result = await db.execute(
        select(ClubLineup).where(ClubLineup.club_id == club_id).options(joinedload(ClubLineup.cards).joinedload(ClubLineupCard.club_card))
    )
    return result.unique().scalar_one_or_none()


def _club_card_to_out(card: ClubCard, in_lineup_ids: set[int]) -> ClubCardOut:
    return ClubCardOut(
        id=card.id, serial_number=card.serial_number, player=PlayerOut.model_validate(card.player),
        acquired_at=card.acquired_at, is_in_lineup=card.id in in_lineup_ids,
    )


async def list_club_cards(db: AsyncSession, user: User) -> list[ClubCardOut]:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    cards = (await db.execute(select(ClubCard).where(ClubCard.club_id == membership.club_id).order_by(ClubCard.acquired_at))).scalars().all()
    lineup = await _get_or_none_lineup(db, membership.club_id)
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()
    return [_club_card_to_out(c, in_lineup_ids) for c in cards]


async def _lineup_to_out(db: AsyncSession, club_id: int) -> ClubLineupOut:
    lineup = await _get_or_none_lineup(db, club_id)
    by_slot = {lc.slot_code: lc.club_card for lc in lineup.cards} if lineup else {}
    in_lineup_ids = {lc.club_card_id for lc in lineup.cards} if lineup else set()

    slots = []
    cards_with_slots = []
    for slot in FORMATION_SLOTS:
        card = by_slot.get(slot.code)
        slots.append(
            ClubLineupSlotOut(
                slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
                card=_club_card_to_out(card, in_lineup_ids) if card else None,
            )
        )
        if card:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(FORMATION_SLOTS)
    team_strength = calculate_base_strength(cards_with_slots) if is_complete else None
    return ClubLineupOut(is_complete=is_complete, team_strength=team_strength, slots=slots)


async def get_club_lineup(db: AsyncSession, user: User) -> ClubLineupOut:
    from app.services.club_service import _require_membership

    membership = await _require_membership(db, user.id)
    return await _lineup_to_out(db, membership.club_id)


async def set_club_lineup(db: AsyncSession, user: User, payload: ClubLineupSetRequest) -> ClubLineupOut:
    from app.services.club_service import _require_manager, _require_membership

    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    club_id = membership.club_id

    slot_codes = [s.slot_code for s in payload.slots]
    if len(slot_codes) != len(set(slot_codes)):
        raise ConflictError("Один слот не может использоваться дважды")
    if any(code not in SLOTS_BY_CODE for code in slot_codes):
        raise ConflictError("Неизвестный слот состава")

    card_ids = [s.club_card_id for s in payload.slots]
    if len(card_ids) != len(set(card_ids)):
        raise ConflictError("Одна карточка не может занимать два слота")

    club_cards = (await db.execute(select(ClubCard).where(ClubCard.id.in_(card_ids), ClubCard.club_id == club_id))).scalars().all()
    if len(club_cards) != len(card_ids):
        raise ConflictError("Карточка не принадлежит этому клубу")
    cards_by_id = {c.id: c for c in club_cards}

    # No duplicate-player check across slots, mirroring lineup_service.set_lineup's
    # same rule for personal squads: one player instance per slot.
    player_ids = [cards_by_id[cid].player_id for cid in card_ids]
    if len(player_ids) != len(set(player_ids)):
        raise ConflictError("Один футболист не может занимать две позиции")

    for slot_in in payload.slots:
        slot = SLOTS_BY_CODE[slot_in.slot_code]
        card = cards_by_id[slot_in.club_card_id]
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(f"Игрок на позиции {card.player.position.value} не подходит для слота {slot.code}")

    # Lock the ClubLineup row before the delete-then-recreate below, mirroring
    # lineup_service.set_lineup's own with_for_update() — a club's captain and
    # up to 2 assistants can all submit lineup changes concurrently, so this
    # serializes overlapping submissions instead of racing on the child rows.
    #
    # with_for_update(of=ClubLineup) scopes the row lock to just the
    # `club_lineups` table: joinedload(ClubLineup.cards) is a LEFT OUTER JOIN
    # to club_lineup_cards (and ClubLineupCard.club_card is itself
    # lazy="joined", cascading further outer joins into club_cards/players/
    # card_collections), and a plain FOR UPDATE tries to lock every joined
    # table including the nullable side of those outer joins, which Postgres
    # rejects outright (FeatureNotSupportedError: FOR UPDATE cannot be
    # applied to the nullable side of an outer join). Restricting the lock to
    # club_lineups keeps the eager-loaded cards while avoiding that
    # restriction — same fix as wallet_service.lock_user_for_update.
    lineup_result = await db.execute(
        select(ClubLineup)
        .where(ClubLineup.club_id == club_id)
        .options(joinedload(ClubLineup.cards))
        .with_for_update(of=ClubLineup)
    )
    lineup = lineup_result.unique().scalar_one_or_none()
    if lineup is None:
        raise ConflictError("У клуба ещё нет состава")

    for lc in list(lineup.cards):
        await db.delete(lc)
    await db.flush()
    for slot_in in payload.slots:
        db.add(ClubLineupCard(club_lineup_id=lineup.id, club_card_id=slot_in.club_card_id, slot_code=slot_in.slot_code))
    await db.commit()
    return await _lineup_to_out(db, club_id)
