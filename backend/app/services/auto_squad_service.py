"""One-tap squad building: pick the best owned card for every formation slot
and save it through the regular setters (lineup_service.set_lineup /
personal_squad_service.set_squad_cards), so every existing rule — slot
category, one copy per player, trade/admin locks, the Card Arena diamond
limit — is still enforced by the same code as a manual pick.
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
from app.services.card_skill_catalog import SKILL_DEFINITIONS
from app.services.lineup_service import CATEGORY_POSITIONS


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
    chosen = pick_cards(slots, await owned_cards(db, user.id), "arena", max_diamonds=config.match_max_diamond_cards)
    require_any(chosen)
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
    chosen = pick_cards(slots, await owned_cards(db, user.id), "tournament", preferred_ids=preferred)
    require_any(chosen)
    payload = PersonalSquadSetRequest(
        slots=[PersonalSquadSlotIn(slot_code=code, user_card_id=c.id) for code, c in chosen.items()],
    )
    return await personal_squad_service.set_squad_cards(db, user, payload, template_index)
