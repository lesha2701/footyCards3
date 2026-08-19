from fastapi import APIRouter, Depends, Request, status
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

router = APIRouter(prefix="/admin/leagues", tags=["admin"], dependencies=[Depends(get_current_admin)])


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


@router.delete("/{tier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tier(tier_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    tier = await _get_tier_or_404(db, tier_id)
    await log_action(db, admin.id, "delete_league_tier", "league_tier", tier_id, old_value=LeagueTierOut.model_validate(tier).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.delete(tier)
    await db.commit()


@router.post("/backfill-rewards", response_model=LeagueBackfillResultOut)
async def backfill_rewards(request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = (await db.execute(select(User).where(User.is_banned.is_(False)))).scalars().all()
    rewarded_count = 0
    for user in users:
        granted = await league_service.sync_league_rewards_for_user(db, user, notify_mode="summary")
        if granted:
            rewarded_count += 1
    await log_action(
        db, admin.id, "backfill_league_rewards", "league_tier", None,
        new_value={"rewarded_count": rewarded_count}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return LeagueBackfillResultOut(rewarded_count=rewarded_count)
