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
from app.services import chemistry_service, manager_tactics
from app.services.chemistry_service import ChemistryRules
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.club_tactical_matchup_service import MENTALITIES, PLAYSTYLES
from app.services.game_config_service import get_config
from app.services.lineup_service import CATEGORY_POSITIONS, FormationSlot, slot_fit
from app.services.player_stats_service import card_rating_bonus

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


def _serialize(
    squad: PersonalSquad, rules: ChemistryRules | None = None, frozen: bool = False, live_enabled: bool | None = None,
) -> PersonalSquadOut:
    # Same ownership rule as resolve_active_squad: a traded-away card is not shown.
    by_slot = {c.slot_code: c.user_card for c in squad.cards if c.user_card.owner_id == squad.user_id}
    slots = []
    formation_slots = get_formation_slots(squad.formation)
    chemistry = chemistry_service.compute_chemistry(
        [(by_slot[s.code], s) for s in formation_slots if s.code in by_slot], squad.formation, rules,
        slot_count=len(formation_slots),
        # Shown as a home match: the stadium extra only applies at home.
        coach_country=chemistry_service.coach_country_of(squad.user_coach_card.coach if squad.user_coach_card else None),
        stadium_club=chemistry_service.stadium_club_of(squad.user_stadium_card.stadium if squad.user_stadium_card else None),
    ) if rules is not None else None
    for slot in formation_slots:
        card = by_slot.get(slot.code)
        rating = fit = chem = None
        if card is not None:
            # Same order as the tournament engine (player_tournament_simulation_service._engine_card
            # and lineup_service.calculate_base_strength).
            rating = min(99, card.player.rating + card_rating_bonus(card))
            chem = chemistry.rating_bonus(slot.code) if chemistry is not None else 0
            fit = slot_fit(card.player.position, slot)
        slots.append(PersonalSquadSlotOut(
            slot_code=slot.code, category=slot.category, ideal_position=slot.ideal_position.value,
            user_card_id=card.id if card else None,
            serial_number=card.serial_number if card else None,
            player=card.player if card else None,
            skill_code=card.skill_code if card else None,
            skill_level=card.skill_level if card else None,
            rating=rating, fit_pct=round((fit or 1) * 100), chemistry_bonus=chem or 0,
            match_rating=round(chemistry_service.boosted_rating(rating, chem) * fit) if card else None,
            stars=(card.stars or 0) if card else 0, path_stage=(card.path_stage or 0) if card else 0,
            prestige=(card.prestige or 0) if card else 0,
        ))
    coach = None
    if squad.user_coach_card is not None:
        c = squad.user_coach_card.coach
        # Same construction as lineup_service._serialize_lineup.
        coach = EquippedCoachOut(
            id=c.id, display_name=c.display_name, rarity=c.rarity.value,
            image_path=c.image_path, boosts=c.boosts, country=c.country,
        )
    stadium = None
    if squad.user_stadium_card is not None:
        s = squad.user_stadium_card.stadium
        stadium = EquippedStadiumOut(
            id=s.id, display_name=s.display_name, rarity=s.rarity.value,
            image_path=s.image_path, boost_pct=float(s.boost_pct), club=s.club,
        )
    return PersonalSquadOut(
        template_index=squad.template_index, name=squad.name, is_active=squad.is_active,
        is_complete=all(s.user_card_id is not None for s in slots),
        formation=squad.formation, mentality=squad.mentality, playstyle=squad.playstyle, style=squad.style,
        slots=slots, coach=coach, stadium=stadium,
        # No single team-strength number in this mode (the tournament engine
        # works on per-card ratings and zones), so no strength_bonus either.
        chemistry=chemistry_service.to_out(chemistry, rules, frozen=frozen, live_enabled=live_enabled),
    )


async def chemistry_context(db: AsyncSession, user_id: int) -> tuple[ChemistryRules | None, bool, bool]:
    """(rules, frozen, live_enabled): the chemistry the player's NEXT
    tournament match will actually be played with. While they are in an
    active player tournament that is its frozen rules
    (PlayerTournament.chemistry_rules, None = off for that tournament) and
    frozen=True; otherwise the live GameConfig."""
    from app.models.enums import TournamentStatus
    from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant

    config = await get_config(db)
    live_enabled = bool(config.chemistry_enabled)
    row = (
        await db.execute(
            select(PlayerTournament.chemistry_rules)
            .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
            .where(PlayerTournamentParticipant.user_id == user_id, PlayerTournament.status == TournamentStatus.active)
        )
    ).first()
    if row is not None:
        return chemistry_service.rules_from_dict(row[0]), True, live_enabled
    return chemistry_service.active_rules(config), False, live_enabled


async def _out(db: AsyncSession, user_id: int, template_index: int) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user_id, template_index), *await chemistry_context(db, user_id))


async def list_templates(db: AsyncSession, user: User) -> list[PersonalSquadOut]:
    context = await chemistry_context(db, user.id)
    return [_serialize(t, *context) for t in await _ensure_templates(db, user.id)]


async def get_squad(db: AsyncSession, user: User, template_index: int | None = None) -> PersonalSquadOut:
    return _serialize(await _get_row(db, user.id, template_index), *await chemistry_context(db, user.id))


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
    if payload.style is not None and payload.style not in manager_tactics.STYLES:
        raise ConflictError(f"Неизвестный стиль: {payload.style}")

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
    if payload.style is not None:
        squad.style = payload.style
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


async def active_tactics(db: AsyncSession, user_id: int) -> tuple[str, str]:
    """(style, formation) of the user's active squad — what the tournament
    plays with; the defaults when the user has no squad yet."""
    row = (await db.execute(
        select(PersonalSquad.style, PersonalSquad.formation)
        .where(PersonalSquad.user_id == user_id, PersonalSquad.is_active.is_(True))
    )).first()
    if row is None:
        return manager_tactics.DEFAULT_STYLE, manager_tactics.DEFAULT_FORMATION
    return manager_tactics.clean_style(row[0]), row[1]


async def tactics_view(db: AsyncSession, user: User) -> dict:
    """The tactics rules and the next tournament opponent's style, so the
    player can pick the style that beats it (Card Arena style)."""
    from app.models.enums import TournamentStatus
    from app.models.player_tournament import PlayerTournament, PlayerTournamentParticipant
    from app.services.player_tournament_fixture_service import TOTAL_ROUNDS, generate_fixtures

    config = await get_config(db)
    view = {"rules": manager_tactics.rules_out(config, "ptour"), "next": None}
    tournament = (await db.execute(
        select(PlayerTournament)
        .join(PlayerTournamentParticipant, PlayerTournamentParticipant.tournament_id == PlayerTournament.id)
        .where(PlayerTournamentParticipant.user_id == user.id, PlayerTournament.status == TournamentStatus.active,
               PlayerTournament.rounds_simulated < TOTAL_ROUNDS)
        .order_by(PlayerTournament.id.desc()).limit(1)
    )).scalar_one_or_none()
    if tournament is None:
        return view
    user_ids = list((await db.execute(
        select(PlayerTournamentParticipant.user_id).where(PlayerTournamentParticipant.tournament_id == tournament.id)
        .order_by(PlayerTournamentParticipant.id)
    )).scalars().all())
    try:
        fixtures = generate_fixtures(user_ids)
    except ValueError:
        return view
    round_number = tournament.rounds_simulated + 1
    opponent_id = next(
        (b if a == user.id else a for r, a, b in fixtures if r == round_number and user.id in (a, b)), None,
    )
    if opponent_id is None:
        return view
    opponent = await db.get(User, opponent_id)
    style, formation = await active_tactics(db, user.id)
    their_style, their_formation = await active_tactics(db, opponent_id)
    view["next"] = {
        "round": round_number, "opponent": opponent.full_display_name() if opponent else "Соперник",
        "style": their_style, "formation": their_formation,
        "edge": manager_tactics.edge(style, their_style),
        "mods": manager_tactics.modifiers(style, formation, their_style, config, "ptour"),
    }
    return view
