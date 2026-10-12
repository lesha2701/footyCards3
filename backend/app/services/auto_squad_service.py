"""One-tap squad building: pick the best owned card for every formation slot
and save it through the regular setters (lineup_service.set_lineup /
personal_squad_service.set_squad_cards), so every existing rule — slot
category, one copy per player, trade/admin locks, the Card Arena diamond
limit — is still enforced by the same code as a manual pick.

With neighbour-link chemistry on (chemistry_service), the greedy pick is
then refined by improve_for_chemistry — a bounded local search that may
trade a little raw rating for links worth more in a match. With it off the
greedy result is saved as-is, exactly as before.
"""
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.models.card import UserCard
from app.models.enums import Rarity
from app.models.user import User
from app.services import chemistry_service
from app.services.card_skill_catalog import SKILL_DEFINITIONS
from app.services.chemistry_service import ChemistryRules
from app.services.lineup_service import CATEGORY_POSITIONS, calculate_base_strength


@dataclass(frozen=True)
class SlotSpec:
    code: str
    category: str
    ideal_position: object  # Position


def _skill_bonus(card: UserCard, engine: str) -> int:
    """Tie-break only: a copy whose skill actually acts in this engine and
    fits its position edges out an otherwise equal copy."""
    definition = SKILL_DEFINITIONS.get(card.skill_code or "")
    if not definition or not definition.engine_supported or engine not in definition.engines:
        return 0
    return (card.skill_level or 0) if card.player.position in definition.positions else 0


def pick_cards(
    slots: list[SlotSpec], cards: Iterable[UserCard], engine: str,
    max_diamonds: Optional[int] = None, preferred_ids: frozenset[int] = frozenset(),
) -> dict[str, UserCard]:
    """Greedy, scarcest slots first (GK, then the rest in formation order).
    Per slot: preferred cards (e.g. copied from another squad) first, then
    exact ideal position, then effective rating (diamond bonus included),
    then an active skill. Never uses two copies of one player."""
    pool = [c for c in cards if not c.is_locked_by_admin and not c.is_locked_in_trade]
    chosen: dict[str, UserCard] = {}
    used_players: set[int] = set()
    diamonds = 0
    ordered = sorted(slots, key=lambda s: 0 if s.category == "GK" else 1)
    for slot in ordered:
        best, best_key = None, None
        for card in pool:
            if card.player_id in used_players or card.player.position not in CATEGORY_POSITIONS[slot.category]:
                continue
            if card.player.rarity == Rarity.diamond and max_diamonds is not None and diamonds >= max_diamonds:
                continue
            key = (
                card.id in preferred_ids,
                card.player.position == slot.ideal_position,
                min(99, card.player.rating + (card.diamond_rating_bonus or 0)),
                _skill_bonus(card, engine),
                -card.id,
            )
            if best_key is None or key > best_key:
                best, best_key = card, key
        if best is not None:
            chosen[slot.code] = best
            used_players.add(best.player_id)
            if best.player.rarity == Rarity.diamond:
                diamonds += 1
    return chosen


# Local-search bounds: candidates tried per slot and improvement rounds.
# Each round evaluates at most slots x (CHEM_TOP_RATED + CHEM_TOP_LINKED) +
# slot-pair swaps lineups of 11 cards — milliseconds, even for big collections.
CHEM_TOP_RATED = 6
CHEM_TOP_LINKED = 10
CHEM_MAX_ROUNDS = 25


def _squad_score(chosen: dict[str, UserCard], slots_by_code: dict[str, SlotSpec], formation: str, rules: ChemistryRules) -> tuple:
    """(players on their ideal position, match strength with chemistry) — the
    same priority pick_cards has (ideal position first), then the Card Arena
    strength formula (lineup_service.calculate_base_strength) with each
    card's chemistry bonus; for tournament squads it is a proxy of the
    engine's per-card match ratings, which are rating + chemistry too."""
    pairs = [(card, slots_by_code[code]) for code, card in chosen.items()]
    chemistry = chemistry_service.compute_chemistry(pairs, formation, rules, slot_count=len(slots_by_code))
    on_position = sum(1 for card, slot in pairs if card.player.position == slot.ideal_position)
    return on_position, calculate_base_strength(pairs, chemistry=chemistry)


def _group_key(value) -> Optional[str]:
    # Same normalisation as chemistry_service._group_key.
    if not isinstance(value, str):
        return value
    return " ".join(value.split()) or None


def improve_for_chemistry(
    chosen: dict[str, UserCard], slots: list[SlotSpec], cards: Iterable[UserCard], formation: str,
    rules: ChemistryRules, max_diamonds: Optional[int] = None, fixed_ids: frozenset[int] = frozenset(),
) -> dict[str, UserCard]:
    """Steepest-ascent local search over pick_cards' result: each round tries
    (a) replacing one slot's card with a bench card — the best-rated ones
    for the slot plus the best ones sharing a club or country with a
    neighbour — and (b) swapping two picked cards between slots, and
    applies the single best strict improvement of _squad_score. Same hard
    rules as pick_cards (slot category, one copy per player, locks, diamond
    limit); slots holding a fixed_ids card (copied from another squad) are
    never touched. Deterministic: ties keep the earlier/lower-id choice."""
    slots_by_code = {s.code: s for s in slots}
    pool = [c for c in cards if not c.is_locked_by_admin and not c.is_locked_in_trade]
    neighbours: dict[str, list[str]] = {s.code: [] for s in slots}
    for a, b in chemistry_service.FORMATION_LINKS.get(formation, ()):
        if a in neighbours and b in neighbours:
            neighbours[a].append(b)
            neighbours[b].append(a)

    def fits(card: UserCard, slot: SlotSpec) -> bool:
        return card.player.position in CATEGORY_POSITIONS[slot.category]

    def diamonds_ok(trial: dict[str, UserCard]) -> bool:
        return max_diamonds is None or sum(1 for c in trial.values() if c.player.rarity == Rarity.diamond) <= max_diamonds

    def candidates(slot: SlotSpec, current: dict[str, UserCard]) -> list[UserCard]:
        others = {code: c for code, c in current.items() if code != slot.code}
        taken_players = {c.player_id for c in others.values()}
        taken_ids = {c.id for c in current.values()}
        eligible = [c for c in pool if c.id not in taken_ids and c.player_id not in taken_players and fits(c, slot)]
        by_rating = sorted(
            eligible, key=lambda c: (c.player.position == slot.ideal_position, _effective(c), -c.id), reverse=True,
        )
        near = [others[n].player for n in neighbours[slot.code] if n in others]
        clubs = {_group_key(p.club) for p in near} - {None}
        countries = {_group_key(p.country) for p in near} - {None}
        linked = [c for c in by_rating if _group_key(c.player.club) in clubs or _group_key(c.player.country) in countries]
        seen: set[int] = set()
        out = []
        for c in by_rating[:CHEM_TOP_RATED] + linked[:CHEM_TOP_LINKED]:
            if c.id not in seen:
                seen.add(c.id)
                out.append(c)
        return out

    current = dict(chosen)
    best_score = _squad_score(current, slots_by_code, formation, rules)
    movable = [s for s in slots if current.get(s.code) is None or current[s.code].id not in fixed_ids]
    for _ in range(CHEM_MAX_ROUNDS):
        best_trial = None
        for slot in movable:
            for card in candidates(slot, current):
                trial = {**current, slot.code: card}
                if not diamonds_ok(trial):
                    continue
                score = _squad_score(trial, slots_by_code, formation, rules)
                if score > best_score:
                    best_score, best_trial = score, trial
        for i, slot_a in enumerate(movable):
            for slot_b in movable[i + 1:]:
                card_a, card_b = current.get(slot_a.code), current.get(slot_b.code)
                if card_a is None or card_b is None or not fits(card_a, slot_b) or not fits(card_b, slot_a):
                    continue
                trial = {**current, slot_a.code: card_b, slot_b.code: card_a}
                score = _squad_score(trial, slots_by_code, formation, rules)
                if score > best_score:
                    best_score, best_trial = score, trial
        if best_trial is None:
            break
        current = best_trial
    return current


async def owned_cards(db: AsyncSession, user_id: int) -> list[UserCard]:
    result = await db.execute(
        select(UserCard).where(UserCard.owner_id == user_id).options(joinedload(UserCard.player))
    )
    return list(result.unique().scalars().all())


def require_any(chosen: dict) -> None:
    if not chosen:
        raise ConflictError("Нет подходящих карточек для состава — открой паки, чтобы собрать игроков")


async def auto_arena_lineup(db: AsyncSession, user: User, template_index: int):
    from app.schemas.lineup import LineupSetRequest, LineupSlotIn
    from app.services import lineup_service
    from app.services.game_config_service import get_config

    config = await get_config(db)
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in lineup_service.FORMATION_SLOTS]
    cards = await owned_cards(db, user.id)
    chosen = pick_cards(slots, cards, "arena", max_diamonds=config.match_max_diamond_cards)
    require_any(chosen)
    rules = chemistry_service.active_rules(config)
    if rules is not None:
        chosen = improve_for_chemistry(
            chosen, slots, cards, lineup_service.ARENA_FORMATION, rules, max_diamonds=config.match_max_diamond_cards,
        )
    payload = LineupSetRequest(slots=[LineupSlotIn(slot_code=code, user_card_id=c.id) for code, c in chosen.items()])
    return await lineup_service.set_lineup(db, user, payload, template_index)


async def auto_personal_squad(db: AsyncSession, user: User, template_index: int, copy_from_arena: bool = False):
    from app.schemas.personal_squad import PersonalSquadSetRequest, PersonalSquadSlotIn
    from app.services import lineup_service, personal_squad_service
    from app.services.club_formation_service import get_formation_slots

    squad = await personal_squad_service.get_squad(db, user, template_index)
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in get_formation_slots(squad.formation)]
    preferred: frozenset[int] = frozenset()
    if copy_from_arena:
        arena = await lineup_service.get_active_lineup(db, user)
        preferred = frozenset(s.card.id for s in arena.slots if s.card is not None)
        if not preferred:
            raise ConflictError("Состав Card Arena пуст — копировать нечего")
    cards = await owned_cards(db, user.id)
    chosen = pick_cards(slots, cards, "tournament", preferred_ids=preferred)
    require_any(chosen)
    # The rules the next tournament match will really use (a running
    # tournament's frozen ones, else GameConfig).
    rules, _frozen, _live = await personal_squad_service.chemistry_context(db, user.id)
    if rules is not None:
        chosen = improve_for_chemistry(chosen, slots, cards, squad.formation, rules, fixed_ids=preferred)
    payload = PersonalSquadSetRequest(
        slots=[PersonalSquadSlotIn(slot_code=code, user_card_id=c.id) for code, c in chosen.items()],
    )
    return await personal_squad_service.set_squad_cards(db, user, payload, template_index)


def _effective(card: UserCard) -> int:
    return min(99, card.player.rating + (card.diamond_rating_bonus or 0))


def bench_upgrades(
    slots: list[SlotSpec], current: dict[str, Optional[int]], cards: Iterable[UserCard],
    max_diamonds: Optional[int] = None,
) -> list[dict]:
    """Per slot: the strongest owned card NOT already in the squad that fits
    the slot and beats what is there now (or fills an empty slot). Unlike
    the auto-fill it never reshuffles other slots, so every hint reads as a
    single swap: "поставь Y вместо X, +N"."""
    by_id = {c.id: c for c in cards}
    pool = [c for c in by_id.values() if not c.is_locked_by_admin and not c.is_locked_in_trade]
    in_squad = {cid for cid in current.values() if cid}
    used_players = {by_id[cid].player_id for cid in in_squad if cid in by_id}
    diamonds = sum(1 for cid in in_squad if cid in by_id and by_id[cid].player.rarity == Rarity.diamond)
    hints: list[dict] = []
    for slot in sorted(slots, key=lambda s: 0 if s.category == "GK" else 1):
        now = by_id.get(current.get(slot.code) or -1)
        now_rating = _effective(now) if now else 0
        best = None
        for card in pool:
            if card.id in in_squad or card.player_id in used_players:
                continue
            if card.player.position not in CATEGORY_POSITIONS[slot.category]:
                continue
            is_diamond = card.player.rarity == Rarity.diamond
            swaps_out_diamond = now is not None and now.player.rarity == Rarity.diamond
            if is_diamond and max_diamonds is not None and diamonds - swaps_out_diamond >= max_diamonds:
                continue
            if _effective(card) <= now_rating:
                continue
            if best is None or (_effective(card), -card.id) > (_effective(best), -best.id):
                best = card
        if best is None:
            continue
        used_players.add(best.player_id)
        in_squad.add(best.id)
        if best.player.rarity == Rarity.diamond:
            diamonds += 1
        hints.append({
            "slot_code": slot.code,
            "current_card_id": now.id if now else None,
            "current_name": now.player.display_name if now else None,
            "current_rating": now_rating if now else None,
            "suggested_card_id": best.id,
            "suggested_name": best.player.display_name,
            "suggested_rating": _effective(best),
            "gain": _effective(best) - now_rating,
        })
    return hints


async def arena_bench_upgrades(db: AsyncSession, user: User, template_index: int) -> list[dict]:
    from app.services import lineup_service
    from app.services.game_config_service import get_config

    lineup = await lineup_service.get_active_lineup(db, user, template_index)
    config = await get_config(db)
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in lineup_service.FORMATION_SLOTS]
    current = {s.slot_code: (s.card.id if s.card else None) for s in lineup.slots}
    return bench_upgrades(slots, current, await owned_cards(db, user.id), max_diamonds=config.match_max_diamond_cards)


async def personal_bench_upgrades(db: AsyncSession, user: User, template_index: int) -> list[dict]:
    from app.services import personal_squad_service
    from app.services.club_formation_service import get_formation_slots

    squad = await personal_squad_service.get_squad(db, user, template_index)
    slots = [SlotSpec(s.code, s.category, s.ideal_position) for s in get_formation_slots(squad.formation)]
    current = {s.slot_code: s.user_card_id for s in squad.slots}
    return bench_upgrades(slots, current, await owned_cards(db, user.id))
