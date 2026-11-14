from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.anniversary import AnniversaryClaimOut, AnniversaryRecapOut, AnniversaryStateOut
from app.services import anniversary_service

router = APIRouter(prefix="/anniversary", tags=["anniversary"])


@router.get("", response_model=AnniversaryStateOut)
async def get_state(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await anniversary_service.get_state(db, user)


@router.get("/recap", response_model=AnniversaryRecapOut)
async def get_recap(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"anniversary_recap:{user.id}", max_calls=20, window_seconds=60)
    return await anniversary_service.recap(db, user)


@router.post("/recap/claim", response_model=AnniversaryClaimOut)
async def claim_recap(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"anniversary_claim:{user.id}", max_calls=20, window_seconds=60)
    return await anniversary_service.claim_recap(db, user)


@router.post("/calendar/claim", response_model=AnniversaryClaimOut)
async def claim_calendar(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"anniversary_claim:{user.id}", max_calls=20, window_seconds=60)
    return await anniversary_service.claim_calendar(db, user)


@router.post("/community/claim", response_model=AnniversaryClaimOut)
async def claim_community(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"anniversary_claim:{user.id}", max_calls=20, window_seconds=60)
    return await anniversary_service.claim_community(db, user)
