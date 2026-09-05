from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.models.card import UserCard
from app.models.diamond_upgrade import DiamondUpgradeTier
from app.models.enums import Rarity
from app.models.player import Player
from app.models.user import User
from app.schemas.card import UserCardOut
from app.schemas.diamond_upgrade import DiamondMaterialCardsOut, FeedCardsResult
from app.services.game_config_service import get_config
from app.services.player_stats_service import effective_card_stats
from app.services.wallet_service import lock_user_for_update

_COST_FIELD = {
    Rarity.common: "common_cost",
    Rarity.rare: "rare_cost",
    Rarity.epic: "epic_cost",
    Rarity.legendary: "legendary_cost",
}

# Above the admin-configured cap (default 95, only reachable at all when
# diamond_rating_cap_enabled is off), the upgrade path is fixed rather than
# admin-tunable: a middle band fed by ANY other diamond cards, then a final
# band fed only by duplicates of the exact card being upgraded.
DIAMOND_EXTENSION_BAND_WIDTH = 3  # e.g. cap 95 -> mid 98
DIAMOND_EXTENSION_COST = 10
DIAMOND_ABSOLUTE_MAX_RATING = 99


@dataclass(frozen=True)
class RatingBand:
    kind: str  # "admin_tier" | "any_diamond" | "same_player_diamond"
    cost: Optional[int]  # fixed cost for the two extension bands; resolved per-rarity via DiamondUpgradeTier for admin_tier
    ceiling: int  # rating this band can raise the card up to (not beyond)


def _resolve_band(base_cap: int, current_rating: int) -> RatingBand:
    if current_rating < base_cap:
        return RatingBand(kind="admin_tier", cost=None, ceiling=base_cap)
    mid = min(base_cap + DIAMOND_EXTENSION_BAND_WIDTH, DIAMOND_ABSOLUTE_MAX_RATING)
    if current_rating < mid:
        return RatingBand(kind="any_diamond", cost=DIAMOND_EXTENSION_COST, ceiling=mid)
    return RatingBand(kind="same_player_diamond", cost=DIAMOND_EXTENSION_COST, ceiling=DIAMOND_ABSOLUTE_MAX_RATING)


async def list_tiers(db: AsyncSession) -> list[DiamondUpgradeTier]:
    result = await db.execute(select(DiamondUpgradeTier).order_by(DiamondUpgradeTier.min_rating))
    return list(result.scalars().all())


async def get_effective_rating_cap(db: AsyncSession) -> int:
    """The rating a diamond card's rating cannot be fed PAST — the admin-
    configurable soft cap (default 95) when enabled, otherwise the absolute
    technical ceiling every card is clamped to (99). Never applied
    retroactively: a card already above this (e.g. from before the setting
    existed, or the cap was lowered later) simply can't be fed further —
    it's never downgraded."""
    config = await get_config(db)
    if not config.diamond_rating_cap_enabled:
        return 99
    return min(99, config.diamond_rating_cap)


async def _tier_for_rating(db: AsyncSession, rating: int) -> Optional[DiamondUpgradeTier]:
    result = await db.execute(
        select(DiamondUpgradeTier).where(
            DiamondUpgradeTier.is_active.is_(True),
            DiamondUpgradeTier.min_rating <= rating,
            DiamondUpgradeTier.max_rating > rating,
        )
    )
    return result.scalars().first()


async def feed_cards(
    db: AsyncSession, user: User, diamond_card_id: int, material_card_ids: list[int]
) -> FeedCardsResult:
    if diamond_card_id in material_card_ids:
        raise ConflictError("A diamond card cannot be fed to itself")
    if len(set(material_card_ids)) != len(material_card_ids):
        raise ConflictError("Duplicate cards in the same feed attempt")

    locked_user = await lock_user_for_update(db, user.id)

    all_ids = [diamond_card_id, *material_card_ids]
    result = await db.execute(
        select(UserCard).where(UserCard.id.in_(all_ids)).options(joinedload(UserCard.player))
    )
    cards = {c.id: c for c in result.scalars().all()}
    if len(cards) != len(set(all_ids)):
        raise NotFoundError("Card not found")

    diamond_card = cards[diamond_card_id]
    if diamond_card.owner_id != locked_user.id:
        raise NotFoundError("Card not found")
    if diamond_card.player.rarity != Rarity.diamond:
        raise ConflictError("Only a diamond card can be leveled up this way")
    if diamond_card.is_locked():
        raise ConflictError("This card is locked and cannot be upgraded")

    material_cards = [cards[cid] for cid in material_card_ids]
    for card in material_cards:
        if card.owner_id != locked_user.id:
            raise NotFoundError("Card not found")
        if card.is_locked():
            raise ConflictError("This card is locked and cannot be used as material")

    material_rarity = material_cards[0].player.rarity
    if any(c.player.rarity != material_rarity for c in material_cards):
        raise ConflictError("All material cards must be the same rarity")

    current_rating, _, _ = effective_card_stats(diamond_card.player, diamond_card.diamond_rating_bonus)
    rating_cap = await get_effective_rating_cap(db)
    if current_rating >= rating_cap:
        raise ConflictError(f"This card is already at the maximum rating ({rating_cap})")

    config = await get_config(db)
    band = _resolve_band(config.diamond_rating_cap, current_rating)

    if band.kind == "admin_tier":
        if material_rarity == Rarity.diamond:
            raise ConflictError("Diamond cards cannot be used as feed material at this rating")
        tier = await _tier_for_rating(db, current_rating)
        if tier is None:
            raise ConflictError("Upgrade is not configured yet for this card's current rating")
        cost = getattr(tier, _COST_FIELD[material_rarity])
        if cost is None:
            raise ConflictError(f"{material_rarity.value} cards cannot be used to upgrade at this rating")
    else:
        if material_rarity != Rarity.diamond:
            raise ConflictError("Only diamond cards can be used to upgrade at this rating")
        if band.kind == "same_player_diamond" and any(c.player_id != diamond_card.player_id for c in material_cards):
            raise ConflictError("Only duplicates of this exact card can be used to upgrade at this rating")
        cost = band.cost

    assert cost is not None
    max_gain = min(rating_cap, band.ceiling) - current_rating
    gained = min(len(material_cards) // cost, max_gain)
    if gained <= 0:
        raise ConflictError(f"Need at least {cost} cards of this rarity for +1 rating")

    consumed_count = gained * cost
    for card in material_cards[:consumed_count]:
        await db.delete(card)

    diamond_card.diamond_rating_bonus += gained
    db.add(diamond_card)
    await db.commit()

    result = await db.execute(
        select(UserCard).where(UserCard.id == diamond_card.id).options(joinedload(UserCard.player))
    )
    refreshed = result.scalar_one()

    return FeedCardsResult(
        diamond_card=UserCardOut.model_validate(refreshed),
        material_rarity=material_rarity,
        cards_consumed=consumed_count,
        cards_returned=len(material_cards) - consumed_count,
        rating_gained=gained,
    )


async def get_material_cards(db: AsyncSession, user_id: int, diamond_card_id: int) -> DiamondMaterialCardsOut:
    """Diamond-only material listing for the two fixed extension bands (95-98,
    98-99) — the "admin_tier" band still uses the existing per-rarity
    /upgrade-cards endpoint, so this returns an empty list for it."""
    result = await db.execute(
        select(UserCard)
        .where(UserCard.id == diamond_card_id, UserCard.owner_id == user_id)
        .options(joinedload(UserCard.player))
    )
    diamond_card = result.scalar_one_or_none()
    if diamond_card is None:
        raise NotFoundError("Card not found")
    if diamond_card.player.rarity != Rarity.diamond:
        raise ConflictError("Only a diamond card can be leveled up this way")

    current_rating, _, _ = effective_card_stats(diamond_card.player, diamond_card.diamond_rating_bonus)
    rating_cap = await get_effective_rating_cap(db)
    config = await get_config(db)
    # Mirrors feed_cards' own gate: with the cap enabled, a card sitting at
    # or above it can never reach an extension band, whatever _resolve_band
    # alone would say — so it stops here rather than advertising a feed
    # that would immediately 409.
    if current_rating >= rating_cap:
        return DiamondMaterialCardsOut(kind="admin_tier", cost=None, ceiling=rating_cap, cards=[])

    band = _resolve_band(config.diamond_rating_cap, current_rating)

    if band.kind == "admin_tier":
        return DiamondMaterialCardsOut(kind=band.kind, cost=band.cost, ceiling=band.ceiling, cards=[])

    query = (
        select(UserCard)
        .join(Player)
        .where(
            UserCard.owner_id == user_id,
            UserCard.id != diamond_card_id,
            Player.rarity == Rarity.diamond,
            UserCard.is_locked_by_admin.is_(False),
            UserCard.is_locked_in_trade.is_(False),
            UserCard.is_in_lineup.is_(False),
            UserCard.is_in_tactico_squad.is_(False),
        )
    )
    if band.kind == "same_player_diamond":
        query = query.where(UserCard.player_id == diamond_card.player_id)

    result = await db.execute(query.options(joinedload(UserCard.player)).order_by(Player.rating.desc()))
    cards = list(result.unique().scalars().all())

    return DiamondMaterialCardsOut(kind=band.kind, cost=band.cost, ceiling=band.ceiling, cards=cards)
