from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.daily_reward import DailyRewardCalendarOut, DailyRewardClaimOut
from app.services import daily_reward_service

router = APIRouter(prefix="/daily-rewards", tags=["daily-rewards"])


@router.get("/calendar", response_model=DailyRewardCalendarOut)
async def get_calendar(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await daily_reward_service.get_calendar(db, user)


@router.post("/claim", response_model=DailyRewardClaimOut)
async def claim_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await daily_reward_service.claim_daily_reward(db, user)
