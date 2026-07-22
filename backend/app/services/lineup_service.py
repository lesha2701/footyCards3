from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.card import UserCard
from app.models.enums import RARITY_ORDER, Position
from app.models.lineup import Lineup, LineupCard
from app.models.user import User
from app.schemas.lineup import LineupOut, LineupSetRequest, LineupSlotOut


@dataclass(frozen=True)
class FormationSlot:
    code: str
    category: str
    ideal_position: Position


FORMATION_SLOTS: list[FormationSlot] = [
    FormationSlot("GK", "GK", Position.GK),
    FormationSlot("DEF1", "DEF", Position.LB),
    FormationSlot("DEF2", "DEF", Position.CB),
    FormationSlot("DEF3", "DEF", Position.CB),
    FormationSlot("DEF4", "DEF", Position.RB),
    FormationSlot("MID1", "MID", Position.CDM),
    FormationSlot("MID2", "MID", Position.CM),
    FormationSlot("MID3", "MID", Position.CAM),
    FormationSlot("FWD1", "FWD", Position.LW),
    FormationSlot("FWD2", "FWD", Position.ST),
    FormationSlot("FWD3", "FWD", Position.RW),
]
SLOTS_BY_CODE = {s.code: s for s in FORMATION_SLOTS}

CATEGORY_POSITIONS = {
    "GK": {Position.GK},
    "DEF": {Position.LB, Position.CB, Position.RB},
    "MID": {Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM},
    "FWD": {Position.LW, Position.ST, Position.RW},
}


async def _get_or_create_lineup(db: AsyncSession, user_id: int) -> Lineup:
    result = await db.execute(
        select(Lineup).where(Lineup.user_id == user_id, Lineup.is_active.is_(True)).options(joinedload(Lineup.cards))
    )
    lineup = result.unique().scalar_one_or_none()
    if lineup is None:
        lineup = Lineup(user_id=user_id, formation="4-3-3", is_active=True)
        db.add(lineup)
        await db.flush()
    return lineup


def calculate_base_strength(cards_with_slots: list[tuple[UserCard, FormationSlot]]) -> int:
    if not cards_with_slots:
        return 0

    total = 0.0
    for card, slot in cards_with_slots:
        player = card.player
        if player.position == slot.ideal_position:
            fit = 1.0
        elif player.position in CATEGORY_POSITIONS[slot.category]:
            fit = 0.9
        else:
            fit = 0.75
        total += player.rating * fit

    avg_rarity = sum(RARITY_ORDER[c.player.rarity] for c, _ in cards_with_slots) / len(cards_with_slots)
    total *= 1 + 0.03 * avg_rarity

    clubs = Counter(c.player.club for c, _ in cards_with_slots)
    countries = Counter(c.player.country for c, _ in cards_with_slots)
    chemistry_bonus = (clubs.most_common(1)[0][1] - 1) * 2 + (countries.most_common(1)[0][1] - 1) * 1
    total += chemistry_bonus

    return round(total)


async def get_active_lineup(db: AsyncSession, user: User) -> LineupOut:
    lineup = await _get_or_create_lineup(db, user.id)
    result = await db.execute(select(LineupCard).where(LineupCard.lineup_id == lineup.id))
    lineup_cards = result.scalars().all()

    card_ids = [lc.user_card_id for lc in lineup_cards]
    cards_by_id: dict[int, UserCard] = {}
    if card_ids:
        cards_result = await db.execute(
            select(UserCard).where(UserCard.id.in_(card_ids)).options(joinedload(UserCard.player))
        )
        cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}

    by_slot_code = {lc.slot_code: cards_by_id.get(lc.user_card_id) for lc in lineup_cards}

    slots_out = []
    cards_with_slots = []
    for slot in FORMATION_SLOTS:
        card = by_slot_code.get(slot.code)
        slots_out.append(
            LineupSlotOut(
                slot_code=slot.code,
                category=slot.category,
                ideal_position=slot.ideal_position.value,
                card=card,
            )
        )
        if card is not None:
            cards_with_slots.append((card, slot))

    is_complete = len(cards_with_slots) == len(FORMATION_SLOTS)
    strength = calculate_base_strength(cards_with_slots) if is_complete else None

    return LineupOut(id=lineup.id, formation=lineup.formation, is_complete=is_complete, team_strength=strength, slots=slots_out)


async def set_lineup(db: AsyncSession, user: User, payload: LineupSetRequest) -> LineupOut:
    slot_codes_seen = set()
    card_ids_seen = set()
    for slot_in in payload.slots:
        if slot_in.slot_code not in SLOTS_BY_CODE:
            raise ConflictError(f"Unknown formation slot: {slot_in.slot_code}")
        if slot_in.slot_code in slot_codes_seen:
            raise ConflictError(f"Duplicate slot in request: {slot_in.slot_code}")
        if slot_in.user_card_id in card_ids_seen:
            raise ConflictError("The same card instance cannot fill two slots")
        slot_codes_seen.add(slot_in.slot_code)
        card_ids_seen.add(slot_in.user_card_id)

    cards_result = await db.execute(
        select(UserCard).where(UserCard.id.in_(card_ids_seen)).options(joinedload(UserCard.player))
    )
    cards_by_id = {c.id: c for c in cards_result.unique().scalars().all()}
    if len(cards_by_id) != len(card_ids_seen):
        raise NotFoundError("One or more cards not found")

    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        slot = SLOTS_BY_CODE[slot_in.slot_code]
        if card.owner_id != user.id:
            raise ForbiddenError("You can only use your own cards in your lineup")
        if card.is_locked_by_admin or card.is_locked_in_trade:
            raise ConflictError(f"Card #{card.serial_number} is locked and cannot be used in a lineup")
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(
                f"Player {card.player.display_name} ({card.player.position.value}) cannot fill a {slot.category} slot"
            )

    lineup = await _get_or_create_lineup(db, user.id)

    old_result = await db.execute(select(LineupCard).where(LineupCard.lineup_id == lineup.id))
    old_lineup_cards = old_result.scalars().all()
    old_card_ids = [lc.user_card_id for lc in old_lineup_cards]
    if old_card_ids:
        old_cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(old_card_ids)))
        for c in old_cards_result.scalars().all():
            c.is_in_lineup = False
            db.add(c)
        for lc in old_lineup_cards:
            await db.delete(lc)
    await db.flush()

    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        card.is_in_lineup = True
        db.add(card)
        db.add(LineupCard(lineup_id=lineup.id, user_card_id=card.id, slot_code=slot_in.slot_code))

    await db.commit()
    return await get_active_lineup(db, user)
