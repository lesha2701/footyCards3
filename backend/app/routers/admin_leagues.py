from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.league import LeagueTier
from app.models.user import User
from app.schemas.league import LeagueBackfillResultOut, LeagueTierCreate, LeagueTierOut, LeagueTierUpdate
from app.services import league_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_league_tier_image, save_league_tier_image
from app.services.wallet_service import lock_user_for_update

router = APIRouter(prefix="/admin/leagues", tags=["admin"], dependencies=[Depends(get_current_admin)])

# Users granted (and committed) per backfill batch — bounds how long any one
# transaction holds its row locks; see backfill_rewards below.
_BACKFILL_BATCH_SIZE = 200


async def _get_tier_or_404(db: AsyncSession, tier_id: int) -> LeagueTier:
    tier = await db.get(LeagueTier, tier_id)
    if tier is None:
        raise NotFoundError("League tier not found")
    return tier


@router.get("", response_model=list[LeagueTierOut])
async def list_all_tiers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(LeagueTier).order_by(LeagueTier.min_rating))
    return result.scalars().all()


@router.post("", response_model=LeagueTierOut)
async def create_tier(payload: LeagueTierCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = LeagueTier(**payload.model_dump())
    db.add(tier)
    await db.flush()
    await log_action(db, admin.id, "create_league_tier", "league_tier", tier.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    await db.refresh(tier)
    return tier


@router.put("/{tier_id}", response_model=LeagueTierOut)
async def update_tier(tier_id: int, payload: LeagueTierUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = await _get_tier_or_404(db, tier_id)
    old_value = LeagueTierOut.model_validate(tier).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tier, key, value)
    db.add(tier)

    await log_action(
        db, admin.id, "update_league_tier", "league_tier", tier_id, old_value=old_value, new_value=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tier)
    return tier


@router.post("/{tier_id}/image", response_model=LeagueTierOut)
async def upload_tier_image(tier_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = await _get_tier_or_404(db, tier_id)
    old_path = tier.image_path
    new_path = await save_league_tier_image(file, tier.name)
    tier.image_path = new_path
    db.add(tier)
    delete_league_tier_image(old_path)
    await log_action(
        db, admin.id, "upload_league_tier_image", "league_tier", tier_id,
        old_value={"image_path": old_path}, new_value={"image_path": new_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tier)
    return tier


@router.delete("/{tier_id}/image", response_model=LeagueTierOut)
async def remove_tier_image(tier_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = await _get_tier_or_404(db, tier_id)
    old_path = tier.image_path
    delete_league_tier_image(old_path)
    tier.image_path = None
    db.add(tier)
    await log_action(
        db, admin.id, "delete_league_tier_image", "league_tier", tier_id,
        old_value={"image_path": old_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tier)
    return tier


@router.delete("/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(tier_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = await _get_tier_or_404(db, tier_id)
    await log_action(db, admin.id, "delete_league_tier", "league_tier", tier_id, old_value=LeagueTierOut.model_validate(tier).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.delete(tier)
    await db.commit()


@router.post("/backfill-rewards", response_model=LeagueBackfillResultOut)
async def backfill_rewards(request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    """Retroactive league-reward pass over the whole (non-banned) player base.

    Each user's row is locked with `lock_user_for_update` before their
    coins/packs are granted — `sync_league_rewards_for_user` credits coins
    and never locks the row itself, so without this a concurrent pack
    purchase / card sale / match reward on the same user could lose an
    update.

    Processed in batches with a commit per batch rather than one
    transaction for everyone: a single unbounded transaction would hold
    every one of those row locks until the very end (blocking coin-mutating
    actions across the entire player base) and would let one conflict — e.g.
    a live tier grant racing this pass into the UserLeagueRewardClaim unique
    constraint — roll the whole run back behind an opaque 500. Because
    `sync_league_rewards_for_user` is idempotent by construction, an
    interrupted run is safely resumed by simply calling this endpoint again.
    """
    user_ids = (
        await db.execute(select(User.id).where(User.is_banned.is_(False)).order_by(User.id))
    ).scalars().all()

    rewarded_count = 0
    for start in range(0, len(user_ids), _BACKFILL_BATCH_SIZE):
        for user_id in user_ids[start : start + _BACKFILL_BATCH_SIZE]:
            locked_user = await lock_user_for_update(db, user_id)
            granted = await league_service.sync_league_rewards_for_user(db, locked_user, notify_mode="summary")
            if granted:
                rewarded_count += 1
        await db.commit()

    await log_action(
        db, admin.id, "backfill_league_rewards", "league_tier", None,
        new_value={"rewarded_count": rewarded_count}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return LeagueBackfillResultOut(rewarded_count=rewarded_count)
