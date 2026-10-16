"""One reward slot = up to five things at once: coins, a pack, a random card
of a rarity, a badge and a cosmetic. Shared by the login calendar, the club
pass, the season pass and the starter offer, so they all preview ("what's
inside") and grant the same way."""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badge import Badge, UserBadge
from app.models.enums import CardSource, Rarity, TransactionType
from app.models.monetization import Cosmetic
from app.models.pack import Pack
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.card import UserCardOut
from app.schemas.monetization import CosmeticOut, GrantedRewardsOut, RewardBundleIn, RewardBundleOut


@dataclass
class Bundle:
    coins: int = 0
    pack_id: Optional[int] = None
    card_rarity: Optional[str] = None
    badge_id: Optional[int] = None
    cosmetic_id: Optional[int] = None

    @classmethod
    def of(cls, row, prefix: str = "") -> "Bundle":
        """From any row carrying <prefix>coins/pack_id/card_rarity/badge_id/cosmetic_id."""
        return cls(
            coins=getattr(row, f"{prefix}coins") or 0,
            pack_id=getattr(row, f"{prefix}pack_id"),
            card_rarity=getattr(row, f"{prefix}card_rarity"),
            badge_id=getattr(row, f"{prefix}badge_id"),
            cosmetic_id=getattr(row, f"{prefix}cosmetic_id"),
        )

    @classmethod
    def from_in(cls, data: RewardBundleIn) -> "Bundle":
        return cls(**data.model_dump(include={"coins", "pack_id", "card_rarity", "badge_id", "cosmetic_id"}))

    def to_in(self) -> RewardBundleIn:
        return RewardBundleIn(
            coins=self.coins, pack_id=self.pack_id, card_rarity=self.card_rarity,
            badge_id=self.badge_id, cosmetic_id=self.cosmetic_id,
        )

    def is_empty(self) -> bool:
        return not (self.coins or self.pack_id or self.card_rarity or self.badge_id or self.cosmetic_id)


async def validate(db: AsyncSession, bundle: Bundle) -> None:
    """Admin input check: every referenced pack/badge/cosmetic exists."""
    from app.core.exceptions import ConflictError

    if bundle.pack_id is not None and await db.get(Pack, bundle.pack_id) is None:
        raise ConflictError(f"Пак #{bundle.pack_id} не найден")
    if bundle.badge_id is not None and await db.get(Badge, bundle.badge_id) is None:
        raise ConflictError(f"Значок #{bundle.badge_id} не найден")
    if bundle.cosmetic_id is not None and await db.get(Cosmetic, bundle.cosmetic_id) is None:
        raise ConflictError(f"Косметика #{bundle.cosmetic_id} не найдена")
    if bundle.card_rarity is not None and bundle.card_rarity not in Rarity.__members__:
        raise ConflictError("Неизвестная редкость карточки")


async def describe(db: AsyncSession, bundle: Bundle) -> RewardBundleOut:
    pack = await db.get(Pack, bundle.pack_id) if bundle.pack_id else None
    badge = await db.get(Badge, bundle.badge_id) if bundle.badge_id else None
    cosmetic = await db.get(Cosmetic, bundle.cosmetic_id) if bundle.cosmetic_id else None
    return RewardBundleOut(
        coins=bundle.coins,
        pack_id=pack.id if pack else None,
        pack_name=pack.name if pack else None,
        card_rarity=bundle.card_rarity,
        badge=BadgeOut.model_validate(badge) if badge else None,
        cosmetic=CosmeticOut.model_validate(cosmetic) if cosmetic else None,
    )


async def grant_badge(db: AsyncSession, user: User, badge_id: int) -> Optional[Badge]:
    """Idempotent; equips it only when the player shows no badge yet."""
    badge = await db.get(Badge, badge_id)
    if badge is None:
        return None
    owned = (await db.execute(
        select(UserBadge.id).where(UserBadge.user_id == user.id, UserBadge.badge_id == badge_id)
    )).first()
    if not owned:
        db.add(UserBadge(user_id=user.id, badge_id=badge_id))
    if user.active_badge_id is None:
        user.active_badge_id = badge_id
        db.add(user)
    return badge


async def grant(
    db: AsyncSession,
    user: User,
    bundle: Bundle,
    *,
    tx_type: TransactionType,
    description: str,
    card_source: CardSource,
    idempotency_prefix: str,
    cosmetic_source: str,
    related_object_type: Optional[str] = None,
    related_object_id: Optional[int] = None,
) -> GrantedRewardsOut:
    """Grants every part of the bundle. `user` must already be row-locked
    (wallet_service.lock_user_for_update); the caller commits."""
    from app.services import collection_service, cosmetic_service
    from app.services.card_creation import create_user_card
    from app.services.pack_service import grant_bonus_pack_opening, pick_random_player
    from app.services.wallet_service import credit_coins

    out = GrantedRewardsOut()
    if bundle.coins > 0:
        await credit_coins(
            db, user, bundle.coins, tx_type, description,
            related_object_type=related_object_type, related_object_id=related_object_id,
        )
        out.coins = bundle.coins

    touched: list[int] = []
    if bundle.pack_id is not None:
        opened = await grant_bonus_pack_opening(
            db, user, bundle.pack_id, idempotency_prefix=idempotency_prefix, source=card_source,
        )
        if opened is not None:
            out.pack_name = opened.pack.name
            out.cards.extend(item.card for item in opened.cards)
            touched.extend(item.card.player.id for item in opened.cards)

    if bundle.card_rarity:
        player = await pick_random_player(db, Rarity(bundle.card_rarity))
        card = await create_user_card(db, user.id, player.id, card_source)
        card.player = player
        out.cards.append(UserCardOut.model_validate(card))
        touched.append(player.id)

    if touched:
        await collection_service.grant_collection_rewards_for_new_cards(db, user, touched)

    if bundle.badge_id is not None:
        badge = await grant_badge(db, user, bundle.badge_id)
        out.badge = BadgeOut.model_validate(badge) if badge else None

    if bundle.cosmetic_id is not None:
        cosmetic = await cosmetic_service.grant(db, user.id, bundle.cosmetic_id, cosmetic_source)
        out.cosmetic = CosmeticOut.model_validate(cosmetic) if cosmetic else None

    out.new_balance = user.balance
    return out
