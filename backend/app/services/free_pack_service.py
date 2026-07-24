from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.core.timeutil import ensure_aware
from app.models.enums import CardSource
from app.models.pack import Pack, PackOpening
from app.models.user import User
from app.schemas.free_pack import FreePackStatusOut
from app.schemas.pack import PackOpenResult, PackOut
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


async def _grant_free_pack(db: AsyncSession, user: User, slug: str) -> Optional[PackOpenResult]:
    # Deferred: avoids a circular import with pack_service.
    from app.services.pack_service import _duplicate_counts_snapshot, roll_and_create_cards, track_pack_opened_tasks

    result = await db.execute(
        select(Pack).where(Pack.slug == slug).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"free-pack-{user.id}-{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    dup_counts = await _duplicate_counts_snapshot(db, user.id)
    opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, CardSource.free_pack)
    await track_pack_opened_tasks(db, user, dup_counts)

    return PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=opened_items, new_balance=user.balance)


async def claim_free_pack(db: AsyncSession, user: User) -> PackOpenResult:
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

    grant_result = await _grant_free_pack(db, locked_user, config.free_pack_pack_slug)
    if grant_result is None:
        raise ConflictError("Free pack is not configured correctly; contact support")

    next_available_at = datetime.now(timezone.utc) + timedelta(hours=config.free_pack_interval_hours)
    locked_user.free_pack_available_at = next_available_at
    locked_user.free_pack_notified = False
    db.add(locked_user)
    await db.commit()
    await db.refresh(locked_user)

    grant_result.new_balance = locked_user.balance
    return grant_result
