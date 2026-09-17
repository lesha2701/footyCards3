from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.enums import RARITY_ORDER, Position, Rarity
from app.models.lineup import Lineup, LineupCard
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
from app.schemas.lineup import EquippedCoachOut, LineupCoachSetRequest, LineupOut, LineupSetRequest, LineupSlotOut, UserCoachCardOut
from app.services.coach_boost_service import arena_rarity_team_strength_bonus
from app.services.game_config_service import get_config
from app.services.player_stats_service import effective_card_stats


def clean_group_key(value):
    """Collapses whitespace inconsistencies (leading/trailing/internal runs)
    in a player's free-text club/country string, so two DB rows meant to
    name the same group (e.g. one entered with a trailing space) always
    count as ONE synergy group for chemistry purposes. Shared by every
    chemistry-bonus computation in the codebase (this module's own
    calculate_base_strength below, and fut_draft_service's separate,
    bigger club/country bonus) — without it, a group can silently split
    into two smaller entries, which under-counts the bonus (two groups of
    2 pay less than one group of 4) and, where a per-group breakdown is
    shown to the player (FUT Draft's chemistry hints), displays the exact
    same line twice.

    Passed through unchanged for non-string input — several test fixtures
    (e.g. test_club_tactical_profile_service.py's _FakePlayer) use plain
    placeholder ints for club/country since Counter(...) never actually
    required strings; only real player data needs the whitespace fix."""
    if not isinstance(value, str):
        return value
    return " ".join(value.split())


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

# tactic -> (attack_multiplier, defense_multiplier)
TACTIC_MULTIPLIERS: dict[str, tuple[float, float]] = {
    "attacking": (1.15, 0.85),
    "balanced": (1.0, 1.0),
    "defensive": (0.85, 1.15),
}

# tactic -> category -> multiplier applied to each card's own contribution to
# team_strength in calculate_base_strength. Rewards matching your tactic to
# your squad's real strengths: "attacking"/"defensive" give a real bump to
# FWD/DEF respectively (and nothing elsewhere), "balanced" gives a smaller
# bump to every category — so whichever category your squad is objectively
# strongest in is also the more advantageous tactic to pick.
TACTIC_CATEGORY_MULTIPLIERS: dict[str, dict[str, float]] = {
    "attacking": {"FWD": 1.08},
    "balanced": {"GK": 1.02, "DEF": 1.02, "MID": 1.02, "FWD": 1.02},
    "defensive": {"DEF": 1.08},
}

CATEGORY_POSITIONS = {
    "GK": {Position.GK},
    "DEF": {Position.LB, Position.CB, Position.RB},
    "MID": {Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM},
    "FWD": {Position.LW, Position.ST, Position.RW},
}


TEMPLATE_COUNT = 5
DEFAULT_TEMPLATE_NAMES = {i: f"Шаблон {i}" for i in range(1, TEMPLATE_COUNT + 1)}


def _templates_query(user_id: int):
    # populate_existing=True is required here for the same reason as
    # wallet_service.lock_user_for_update / club_squad_service._get_or_none_lineup:
    # the session's identity map may already hold one of these Lineup
    # objects from earlier in the request (e.g. set_lineup_coach re-fetching
    # after its own commit), and this app's session factory uses
    # expire_on_commit=False (see database.py), so a plain re-SELECT after
    # commit would silently return that stale cached object instead of what
    # this query actually just fetched.
    return (
        select(Lineup)
        .where(Lineup.user_id == user_id)
        .options(
            joinedload(Lineup.cards),
            joinedload(Lineup.user_coach_card).joinedload(UserCoachCard.coach).selectinload(Coach.boosts),
        )
        .order_by(Lineup.template_index)
        .execution_options(populate_existing=True)
    )


async def _ensure_templates(db: AsyncSession, user_id: int) -> list[Lineup]:
    """Lazily seeds any of the 5 fixed template slots that don't exist yet
    for this user — same lazy-singleton-row pattern as game_config_service
    .get_config and daily_reward_service.get_day_options, just seeding up
    to 5 rows instead of 1. A brand-new user gets all 5 on their first
    lineup-related request; an existing user (who already has their single
    pre-migration row at template_index=1) gets templates 2-5 filled in."""
    result = await db.execute(_templates_query(user_id))
    templates = list(result.unique().scalars().all())
    existing_indexes = {t.template_index for t in templates}
    missing = [i for i in range(1, TEMPLATE_COUNT + 1) if i not in existing_indexes]
    if not missing:
        return templates

    has_active = any(t.is_active for t in templates)
    try:
        # A SAVEPOINT (not a full db.rollback()) so a lost race only undoes
        # this one failed insert batch — a plain rollback expires every
        # object in the session, including the caller's already-loaded
        # `user`, which then blows up with a greenlet error the next time
        # something touches it.
        async with db.begin_nested():
            for i in missing:
                db.add(Lineup(
                    user_id=user_id, template_index=i, name=DEFAULT_TEMPLATE_NAMES[i],
                    formation="4-3-3", is_active=(i == 1 and not has_active),
                ))
            await db.flush()
    except IntegrityError:
        # Lost a race with a concurrent first-time request for this same
        # user (uq_lineup_user_template / uq_lineup_one_active_per_user) —
        # the winner's rows are what we want, not a second set.
        pass

    result = await db.execute(_templates_query(user_id))
    return list(result.unique().scalars().all())


async def _get_template_row(db: AsyncSession, user_id: int, template_index: int | None) -> Lineup:
    templates = await _ensure_templates(db, user_id)
    if template_index is None:
        return next(t for t in templates if t.is_active)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    return next(t for t in templates if t.template_index == template_index)


def calculate_base_strength(
    cards_with_slots: list[tuple[UserCard, FormationSlot]],
    coach: "Coach | None" = None,
    tactic: "str | None" = None,
) -> int:
    if not cards_with_slots:
        return 0

    # tactic=None (the default) applies no category multiplier at all — this
    # keeps club_tactical_profile_service.py, tournament_simulation_service.py
    # and club_squad_service.py (which all call this with a single positional
    # argument, no tactic concept of their own) byte-for-byte unaffected.
    category_multipliers = TACTIC_CATEGORY_MULTIPLIERS.get(tactic, {}) if tactic else {}

    # The rarity bonus is per card (each card's own rarity boosts only its
    # own contribution) rather than based on the team's average rarity —
    # a team-average bonus would apply to the whole sum, so swapping in a
    # single lower-rarity card could shrink the entire team's total even
    # though that card's own rating went up, which read as a bug to players.
    total = 0.0
    for card, slot in cards_with_slots:
        player = card.player
        if player.position == slot.ideal_position:
            fit = 1.0
        elif player.position in CATEGORY_POSITIONS[slot.category]:
            fit = 0.9
        else:
            fit = 0.75
        # club_tactical_profile_service.py reuses this function with ClubCard
        # rows (a separate club-owned card pool with no diamond-leveling
        # concept of its own) alongside personal UserCard rows — getattr
        # keeps this function correct for both instead of forcing an
        # unrelated column onto ClubCard.
        rating, _, _ = effective_card_stats(player, getattr(card, "diamond_rating_bonus", 0))
        category_mult = category_multipliers.get(slot.category, 1.0)
        total += rating * fit * (1 + 0.03 * RARITY_ORDER[player.rarity]) * category_mult

    clubs = Counter(clean_group_key(c.player.club) for c, _ in cards_with_slots)
    countries = Counter(clean_group_key(c.player.country) for c, _ in cards_with_slots)
    chemistry_bonus = (clubs.most_common(1)[0][1] - 1) * 2 + (countries.most_common(1)[0][1] - 1) * 1
    total += chemistry_bonus
    total += arena_rarity_team_strength_bonus(coach)

    return round(total)


def split_strength(strength: int, tactic: str) -> tuple[int, int]:
    """Splits a single strength number into (attack, defense) per the tactic's multipliers."""
    attack_mult, defense_mult = TACTIC_MULTIPLIERS.get(tactic, TACTIC_MULTIPLIERS["balanced"])
    return max(1, round(strength * attack_mult)), max(1, round(strength * defense_mult))


async def _serialize_lineup(db: AsyncSession, lineup: Lineup) -> LineupOut:
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
    coach = lineup.user_coach_card.coach if lineup.user_coach_card else None
    strength = calculate_base_strength(cards_with_slots, coach=coach, tactic=lineup.tactic) if is_complete else None
    config = await get_config(db)

    return LineupOut(
        id=lineup.id, template_index=lineup.template_index, name=lineup.name, is_active=lineup.is_active,
        formation=lineup.formation, tactic=lineup.tactic, is_complete=is_complete,
        team_strength=strength, max_diamond=config.match_max_diamond_cards,
        coach=EquippedCoachOut(
            id=coach.id, display_name=coach.display_name, rarity=coach.rarity.value,
            image_path=coach.image_path, boosts=coach.boosts,
        ) if coach else None,
        slots=slots_out,
    )


async def set_tactic(db: AsyncSession, user: User, tactic: str, template_index: int | None = None) -> LineupOut:
    if tactic not in TACTIC_MULTIPLIERS:
        raise ConflictError(f"Unknown tactic: {tactic}")
    lineup = await _get_template_row(db, user.id, template_index)
    lineup.tactic = tactic
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)


async def get_active_lineup(db: AsyncSession, user: User, template_index: int | None = None) -> LineupOut:
    lineup = await _get_template_row(db, user.id, template_index)
    return await _serialize_lineup(db, lineup)


async def list_templates(db: AsyncSession, user: User) -> list[LineupOut]:
    templates = await _ensure_templates(db, user.id)
    return [await _serialize_lineup(db, t) for t in templates]


async def list_user_coach_cards(db: AsyncSession, user: User) -> list[UserCoachCardOut]:
    """GET /lineups/coach-cards — list all coaches owned by the user, mirroring
    club_squad_service.list_club_coach_cards."""
    result = await db.execute(
        select(UserCoachCard)
        .where(UserCoachCard.user_id == user.id)
        .options(joinedload(UserCoachCard.coach).selectinload(Coach.boosts))
        .order_by(UserCoachCard.id)
    )
    return result.unique().scalars().all()


async def set_lineup_coach(
    db: AsyncSession, user: User, payload: LineupCoachSetRequest, template_index: int | None = None
) -> LineupOut:
    lineup = await _get_template_row(db, user.id, template_index)
    if payload.user_coach_card_id is not None:
        card = await db.get(UserCoachCard, payload.user_coach_card_id)
        if card is None or card.user_id != user.id:
            raise ConflictError("Тренер не найден в вашей коллекции")
    lineup.user_coach_card_id = payload.user_coach_card_id
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)


async def rename_template(db: AsyncSession, user: User, template_index: int, name: str) -> LineupOut:
    if not name.strip():
        raise ConflictError("Название не может быть пустым")
    lineup = await _get_template_row(db, user.id, template_index)
    lineup.name = name.strip()[:64]
    db.add(lineup)
    await db.commit()
    return await get_active_lineup(db, user, template_index)


async def set_lineup(
    db: AsyncSession, user: User, payload: LineupSetRequest, template_index: int | None = None
) -> LineupOut:
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

    player_ids_seen: set[int] = set()
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
        if card.player_id in player_ids_seen:
            raise ConflictError(
                f"Player {card.player.display_name} is already assigned to another slot; even duplicate copies can't fill two slots"
            )
        player_ids_seen.add(card.player_id)

    config = await get_config(db)
    diamond_count = sum(1 for card in cards_by_id.values() if card.player.rarity == Rarity.diamond)
    if diamond_count > config.match_max_diamond_cards:
        raise ConflictError(f"Максимум {config.match_max_diamond_cards} диамантовых карт в составе")

    lineup = await _get_template_row(db, user.id, template_index)

    # Locks the lineup row so two overlapping PUTs for the same template
    # (e.g. tapping a second slot before the first pick's request has
    # returned) serialize instead of racing — see this function's original
    # comment (behavior unchanged, just scoped to one template row instead
    # of the user's only row).
    #
    # with_for_update(of=Lineup) scopes the row lock to just the `lineups`
    # table: Lineup.user_coach_card is lazy="joined", so a bare
    # select(Lineup) always carries a LEFT OUTER JOIN to user_coach_cards
    # (and transitively coaches) even though no coach data is used here —
    # and a plain FOR UPDATE tries to lock that nullable-side join too,
    # which Postgres rejects outright (FeatureNotSupportedError: FOR UPDATE
    # cannot be applied to the nullable side of an outer join). Same fix as
    # wallet_service.lock_user_for_update / club_squad_service's own
    # with_for_update(of=ClubLineup).
    await db.execute(select(Lineup).where(Lineup.id == lineup.id).with_for_update(of=Lineup))

    old_result = await db.execute(select(LineupCard).where(LineupCard.lineup_id == lineup.id))
    old_lineup_cards = old_result.scalars().all()
    old_card_ids = [lc.user_card_id for lc in old_lineup_cards]

    # Trade/upgrade locking reflects only the ACTIVE template — editing a
    # template that isn't currently active must never touch is_in_lineup on
    # any card (cards parked in inactive templates stay freely tradeable).
    if lineup.is_active and old_card_ids:
        old_cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(old_card_ids)))
        for c in old_cards_result.scalars().all():
            c.is_in_lineup = False
            db.add(c)
    for lc in old_lineup_cards:
        await db.delete(lc)
    await db.flush()

    for slot_in in payload.slots:
        card = cards_by_id[slot_in.user_card_id]
        if lineup.is_active:
            card.is_in_lineup = True
            db.add(card)
        db.add(LineupCard(lineup_id=lineup.id, user_card_id=card.id, slot_code=slot_in.slot_code))

    await db.commit()
    return await get_active_lineup(db, user, lineup.template_index)


async def activate_template(db: AsyncSession, user: User, template_index: int) -> LineupOut:
    """Switches which of the user's 5 templates is active, recomputing
    UserCard.is_in_lineup for exactly the cards whose lock status changes:
    cards exclusive to the old active template are unlocked, cards in the
    new active template are locked, and cards present in BOTH stay locked
    throughout (computed as a set difference before any writes, so there's
    no window where a shared card is momentarily unlocked)."""
    templates = await _ensure_templates(db, user.id)
    if not 1 <= template_index <= TEMPLATE_COUNT:
        raise NotFoundError(f"template_index must be between 1 and {TEMPLATE_COUNT}")
    new_active = next(t for t in templates if t.template_index == template_index)
    old_active = next((t for t in templates if t.is_active), None)

    if old_active is not None and old_active.id == new_active.id:
        return await get_active_lineup(db, user, template_index)

    lock_ids = [t.id for t in (old_active, new_active) if t is not None]
    await db.execute(select(Lineup).where(Lineup.id.in_(lock_ids)).with_for_update(of=Lineup))

    old_card_ids: set[int] = set()
    if old_active is not None:
        old_result = await db.execute(select(LineupCard.user_card_id).where(LineupCard.lineup_id == old_active.id))
        old_card_ids = set(old_result.scalars().all())
    new_result = await db.execute(select(LineupCard.user_card_id).where(LineupCard.lineup_id == new_active.id))
    new_card_ids = set(new_result.scalars().all())

    to_unlock = old_card_ids - new_card_ids
    to_lock = new_card_ids - old_card_ids
    touched_ids = to_unlock | to_lock
    if touched_ids:
        cards_result = await db.execute(select(UserCard).where(UserCard.id.in_(touched_ids)))
        for card in cards_result.scalars().all():
            card.is_in_lineup = card.id in to_lock
            db.add(card)

    if old_active is not None:
        old_active.is_active = False
        db.add(old_active)
        # Flushed separately from setting the new row active: the partial
        # unique index uq_lineup_one_active_per_user is checked per
        # statement, not deferred to commit, and SQLAlchemy's flush doesn't
        # guarantee these two UPDATEs execute in db.add() order (same-table
        # updates can be batched via executemany in an order keyed off the
        # identity map, not call order) — without this, deactivating the
        # old row and activating the new one can land in the wrong order
        # and collide on the index (observed directly: activating a
        # lower-id template while a higher-id one was active raised
        # UniqueViolationError instead of switching).
        await db.flush()
    new_active.is_active = True
    db.add(new_active)

    await db.commit()
    return await get_active_lineup(db, user, template_index)
