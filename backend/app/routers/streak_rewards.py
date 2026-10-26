from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import streak_reward_service

router = APIRouter(prefix="/streak-rewards", tags=["streak-rewards"])


class StreakRewardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    days: int
    rewards: dict
    granted_at: datetime
    seen_at: Optional[datetime] = None


@router.get("/unseen", response_model=list[StreakRewardOut])
async def unseen(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await streak_reward_service.unseen(db, user)


@router.post("/{reward_id}/seen", status_code=204)
async def seen(reward_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await streak_reward_service.mark_seen(db, user, reward_id)
