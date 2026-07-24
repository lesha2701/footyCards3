from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import CardSource
from app.models.pack import Pack, PackOpening, PackOpeningCard
from app.models.user import User
from app.schemas.card import UserCardOut
from app.schemas.free_pack import FreePackClaimOut, FreePackStatusOut
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.wallet_service import lock_user_for_update


def _is_available(user: User) -> bool:
    if user.free_pack_available_at is None:
        return True
    return ensure_aware(user.free_pack_available_at) <= datetime.now(timezone.utc)


async def get_status(db: AsyncSession, user: User) -> FreePackStatusOut:
    if _is_available(user):
        return FreePackStatusOut(available=True, available_at=None)
    return FreePackStatusOut(available=False, available_at=user.free_pack_available_at)


async def _grant_free_pack(db: AsyncSession, user: User, slug: str) -> tuple[Optional[str], Optional[UserCard]]:
    from app.services.pack_service import pick_random_player, roll_rarities  # deferred: avoids a circular import with pack_service

    result = await db.execute(
        select(Pack).where(Pack.slug == slug).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None, None

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"free-pack-{user.id}-{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    rarities = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
    last_card = None
    for rarity in rarities:
        player = await pick_random_player(db, rarity)
        card = await create_user_card(db, user.id, player.id, CardSource.free_pack, opening.id)
        db.add(PackOpeningCard(opening_id=opening.id, user_card_id=card.id, is_new_player=False))
        card.player = player
        last_card = card
    return pack.name, last_card


async def claim_free_pack(db: AsyncSession, user: User) -> FreePackClaimOut:
    if not _is_available(user):
        raise ConflictError(
            "Free pack not available yet",
            details={"available_at": user.free_pack_available_at.isoformat()},
        )

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    if not _is_available(locked_user):
        raise ConflictError(
            "Free pack not available yet",
            details={"available_at": locked_user.free_pack_available_at.isoformat()},
        )

    granted_pack_name, granted_card = await _grant_free_pack(db, locked_user, config.free_pack_pack_slug)
    next_available_at = datetime.now(timezone.utc) + timedelta(hours=config.free_pack_interval_hours)
    locked_user.free_pack_available_at = next_available_at
    locked_user.free_pack_notified = False
    db.add(locked_user)
    await db.commit()
    await db.refresh(locked_user)

    return FreePackClaimOut(
        granted_pack_name=granted_pack_name,
        granted_card=UserCardOut.model_validate(granted_card) if granted_card else None,
        new_balance=locked_user.balance,
        next_available_at=next_available_at,
    )
