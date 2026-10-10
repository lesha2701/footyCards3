from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
from app.models.user_stadium_card import UserStadiumCard
from app.schemas.lineup import EquippedCoachOut, EquippedStadiumOut
from app.schemas.personal_squad import (
    PersonalSquadCoachRequest, PersonalSquadOut, PersonalSquadSetRequest, PersonalSquadSlotOut,
    PersonalSquadStadiumRequest, PersonalSquadTacticsRequest,
)
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot

TEMPLATE_COUNT = 5
DEFAULT_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, TEMPLATE_COUNT + 1)}


def _templates_query(user_id: int):
    # populate_existing=True for the same reason as lineup_service._templates_query:
    # expire_on_commit=False means a plain re-SELECT after a commit would return
    # stale cached objects.
    return (
        select(PersonalSquad)
        .where(PersonalSquad.user_id == user_id)
        .options(
            joinedload(PersonalSquad.cards).joinedload(PersonalSquadCard.user_card).joinedload(UserCard.player),
            joinedload(PersonalSquad.user_coach_card).joinedload(UserCoachCard.coach).selectinload(Coach.boosts),
            joinedload(PersonalSquad.user_stadium_card).joinedload(UserStadiumCard.stadium),
        )
        .order_by(PersonalSquad.template_index)
        .execution_options(populate_existing=True)
    )


async def _ensure_templates(db: AsyncSession, user_id: int) -> list[PersonalSquad]:
    """Lazily seeds the 5 fixed template slots (same idea as
    lineup_service._ensure_templates). Template 1 starts active."""
    result = await db.execute(_templates_query(user_id))
    templates = list(result.unique().scalars().all())
    existing = {t.template_index for t in templates}
    missing = [i for i in range(1, TEMPLATE_COUNT + 1) if i not in existing]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        # SAVEPOINT so a lost race only undoes this insert batch instead of
        # expiring the caller's whole session.
        async with db.begin_nested():
            for i in missing:
                db.add(PersonalSquad(
                    user_id=user_id, template_index=i, name=DEFAULT_TEMPLATE_NAMES[i],
                    is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        pass

    result = await db.execute(_templates_query(user_id))
    return list(result.unique().scalars().all())


def _pick(templates: list[PersonalSquad], template_index: int | None) -> PersonalSquad:
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)


async def _get_row(db: AsyncSession, user_id: int, template_index: int | None) -> PersonalSquad:
    return _pick(await _ensure_templates(db, user_id), template_index)


async def _lock_row(db: AsyncSession, user_id: int, template_index: int | None) -> PersonalSquad:
    # Rows must exist before they can be locked, so seed first. Then take the
    # FOR UPDATE (populate_existing) BEFORE reading the squad's state: a plain
    # read followed by a lock would validate against a stale formation/cards
    # snapshot if a concurrent writer committed in between.
    templates = await _ensure_templates(db, user_id)
    target = _pick(templates, template_index)
    # of=PersonalSquad: user_coach_card is lazy="joined" (nullable outer join),
    # which Postgres refuses to FOR UPDATE (see lineup_service.set_lineup).
    await db.execute(
        select(PersonalSquad).where(PersonalSquad.id == target.id)
        .with_for_update(of=PersonalSquad).execution_options(populate_existing=True)
    )
    # Re-read (populate_existing query) so everything downstream sees post-lock state.
    return await _get_row(db, user_id, target.template_index)


def _slots_by_code(formation: str) -> dict[str, FormationSlot]:
    return {s.code: s for s in get_formation_slots(formation)}


def _serialize(squad: PersonalSquad) -> PersonalSquadOut:
    # Same ownership rule as resolve_active_squad: a traded-away card is not shown.
    by_slot = {c.slot_code: c.user_card for c in squad.cards if c.user_card.owner_id == squad.user_id}
    slots = []
    for slot in get_formation_slots(squad.formation):
        card = by_slot.get(slot.code)
        slots.append(PersonalSquadSlotOut(
            slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
            user_card_id=card.id if card else None,
            serial_number=card.serial_number if card else None,
            player=card.player if card else None,
            skill_code=card.skill_code if card else None,
            skill_level=card.skill_level if card else None,
        ))
    coach = None
    if squad.user_coach_card is not None:
        c = squad.user_coach_card.coach
        # Same construction as lineup_service._serialize_lineup.
        coach = EquippedCoachOut(
            id=c.id, display_name=c.display_name, rarity=c.rarity.value,
            image_path=c.image_path, boosts=c.boosts,
        )
    stadium = None
    if squad.user_stadium_card is not None:
        s = squad.user_stadium_card.stadium
        stadium = EquippedStadiumOut(
            id=s.id, display_name=s.display_name, rarity=s.rarity.value,
            image_path=s.image_path, boost_pct=float(s.boost_pct),
        )
    return PersonalSquadOut(
        template_index=squad.template_index, name=squad.name, is_active=squad.is_active,
        is_complete=all(s.user_card_id is not None for s in slots),
        formation=squad.formation, mentality=squad.mentality, playstyle=squad.playstyle,
        slots=slots, coach=coach, stadium=stadium,
    )


async def _out(db: AsyncSession, user_id: int, template_index: int) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user_id, template_index))


async def list_templates(db: AsyncSession, user: User) -> list[PersonalSquadOut]:
    return [_serialize(t) for t in await _ensure_templates(db, user.id)]


async def get_squad(db: AsyncSession, user: User, template_index: int | None = None) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user.id, template_index))


async def set_squad_cards(
    db: AsyncSession, user: User, payload: PersonalSquadSetRequest, template_index: int | None = None
) -> PersonalSquadOut:
    squad = await _lock_row(db, user.id, template_index)
    slots_by_code = _slots_by_code(squad.formation)

    seen_slots: set[str] = set()
    seen_cards: set[int] = set()
    for slot_in in payload.slots:
        if slot_in.slot_code not in slots_by_code:
            raise ConflictError(f"Неизвестная позиция схемы: {slot_in.slot_code}")
        if slot_in.slot_code in seen_slots:
            raise ConflictError(f"Позиция указана дважды: {slot_in.slot_code}")
        if slot_in.user_card_id in seen_cards:
            raise ConflictError("Одна карта не может занимать две позиции")
        seen_slots.add(slot_in.slot_code)
        seen_cards.add(slot_in.user_card_id)

    cards = (
        await db.execute(select(UserCard).where(UserCard.id.in_(seen_cards)).options(joinedload(UserCard.player)))
    ).unique().scalars().all()
    cards_by_id = {c.id: c for c in cards}
    if len(cards_by_id) != len(seen_cards):
        raise NotFoundError("Одна или несколько карт не найдены")

    seen_players: set[int] = set()
    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        slot = slots_by_code[slot_in.slot_code]
        if card.owner_id != user.id:
            raise ForbiddenError("В составе можно использовать только свои карты")
        if card.is_locked_by_admin or card.is_locked_in_trade:
            raise ConflictError("Карта заблокирована и не может быть в составе")
        if card.player.position not in CATEGORY_POSITIONS[slot.category]:
            raise ConflictError(
                f"{card.player.display_name} ({card.player.position.value}) не подходит на позицию {slot.category}"
            )
        if card.player_id in seen_players:
            raise ConflictError(f"{card.player.display_name} уже стоит на другой позиции")
        seen_players.add(card.player_id)

    idx = squad.template_index
    squad_id = squad.id
    for existing in list(squad.cards):
        await db.delete(existing)
    await db.flush()
    for slot_in in payload.slots:
        db.add(PersonalSquadCard(squad_id=squad_id, user_card_id=slot_in.user_card_id, slot_code=slot_in.slot_code))
    await db.commit()
    return await _out(db, user.id, idx)


async def set_tactics(
    db: AsyncSession, user: User, payload: PersonalSquadTacticsRequest, template_index: int | None = None
) -> PersonalSquadOut:
    if payload.formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Неизвестная схема: {payload.formation}")
    if payload.mentality not in MENTALITIES:
        raise ConflictError(f"Неизвестный настрой: {payload.mentality}")
    if payload.playstyle not in PLAYSTYLES:
        raise ConflictError(f"Неизвестный стиль игры: {payload.playstyle}")

    squad = await _lock_row(db, user.id, template_index)
    idx = squad.template_index
    new_slots = _slots_by_code(payload.formation)
    for card in list(squad.cards):
        new_slot = new_slots.get(card.slot_code)
        # Drop cards whose code vanished, or whose code survives but now
        # belongs to a category the card's position doesn't fit.
        if new_slot is None or card.user_card.player.position not in CATEGORY_POSITIONS[new_slot.category]:
            await db.delete(card)
    squad.formation = payload.formation
    squad.mentality = payload.mentality
    squad.playstyle = payload.playstyle
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, idx)


async def set_coach(
    db: AsyncSession, user: User, payload: PersonalSquadCoachRequest, template_index: int | None = None
) -> PersonalSquadOut:
    if payload.user_coach_card_id is not None:
        coach_card = await db.get(UserCoachCard, payload.user_coach_card_id)
        if coach_card is None or coach_card.user_id != user.id:
            raise ConflictError("Тренер не принадлежит тебе")
    squad = await _lock_row(db, user.id, template_index)
    idx = squad.template_index
    squad.user_coach_card_id = payload.user_coach_card_id
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, idx)


async def set_stadium(
    db: AsyncSession, user: User, payload: PersonalSquadStadiumRequest, template_index: int | None = None
) -> PersonalSquadOut:
    if payload.user_stadium_card_id is not None:
        stadium_card = await db.get(UserStadiumCard, payload.user_stadium_card_id)
        if stadium_card is None or stadium_card.user_id != user.id:
            raise ConflictError("Стадион не принадлежит тебе")
    squad = await _lock_row(db, user.id, template_index)
    idx = squad.template_index
    squad.user_stadium_card_id = payload.user_stadium_card_id
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, idx)


async def rename_template(db: AsyncSession, user: User, template_index: int, name: str) -> PersonalSquadOut:
    squad = await _lock_row(db, user.id, template_index)
    idx = squad.template_index
    squad.name = " ".join(name.split())[:64] or DEFAULT_TEMPLATE_NAMES[idx]
    db.add(squad)
    await db.commit()
    return await _out(db, user.id, idx)


async def activate_template(db: AsyncSession, user: User, template_index: int) -> PersonalSquadOut:
    await _ensure_templates(db, user.id)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    # Lock ALL of the user's squad rows in one ordered statement (template_index
    # order, so concurrent activations can't deadlock) BEFORE deciding which is
    # active; otherwise two concurrent activations both flip a stale active row
    # and trip uq_personal_squad_one_active_per_user.
    await db.execute(
        select(PersonalSquad).where(PersonalSquad.user_id == user.id)
        .order_by(PersonalSquad.template_index)
        .with_for_update(of=PersonalSquad).execution_options(populate_existing=True)
    )
    templates = await _ensure_templates(db, user.id)
    target = _pick(templates, template_index)
    if not target.is_active:
        for t in templates:
            if t.is_active:
                t.is_active = False
                db.add(t)
        # Flush the deactivation first: the one-active unique index would
        # otherwise see two active rows mid-flush.
        await db.flush()
        target.is_active = True
        db.add(target)
    await db.commit()
    return await _out(db, user.id, template_index)


async def resolve_active_squad(
    db: AsyncSession, user_id: int
) -> tuple[PersonalSquad, list[tuple[UserCard, FormationSlot]]]:
    """Active squad + its (card, slot) pairs for match simulation. Cards the
    user no longer owns (traded away) are silently skipped; a card that was
    sold/deleted is already gone via ON DELETE CASCADE."""
    squad = await _get_row(db, user_id, None)
    slots = _slots_by_code(squad.formation)
    pairs = [
        (pc.user_card, slots[pc.slot_code])
        for pc in squad.cards
        if pc.slot_code in slots and pc.user_card.owner_id == user_id
    ]
    return squad, pairs


async def is_squad_complete(db: AsyncSession, user_id: int) -> bool:
    squad, pairs = await resolve_active_squad(db, user_id)
    return len(pairs) == len(get_formation_slots(squad.formation))
