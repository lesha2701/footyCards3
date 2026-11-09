from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.player import PlayerOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import loyalty_service, shop_product_service, streak_reward_service

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


class LoyaltyRewardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    rewards: dict
    granted_at: datetime
    seen_at: Optional[datetime] = None


class MilestoneOut(BaseModel):
    days: int
    reached: bool
    exclusive: bool
    coins: int
    card_rarity: Optional[str] = None


class StreakSaveOut(BaseModel):
    saved_streak: int
    until: datetime
    restored_streak: int
    price_stars: int
    free_available: bool


class LoyaltyStatusOut(BaseModel):
    enabled: bool
    streak: int
    goal: int
    milestones: list[MilestoneOut]
    centurion: Optional[PlayerOut] = None
    centurion_owned: bool
    streak_save: Optional[StreakSaveOut] = None


class StreakRestoredOut(BaseModel):
    streak: int


@router.get("/status", response_model=LoyaltyStatusOut)
async def status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # A streak bought back (Stars) may have passed a milestone meanwhile.
    await streak_reward_service.check(db, user)
    return await loyalty_service.status(db, user)


@router.get("/unseen", response_model=list[LoyaltyRewardOut])
async def unseen(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await loyalty_service.unseen(db, user)


@router.post("/{reward_id}/seen", status_code=204)
async def seen(reward_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await loyalty_service.mark_seen(db, user, reward_id)


@router.post("/streak-save/free", response_model=StreakRestoredOut)
async def restore_free(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return StreakRestoredOut(streak=await loyalty_service.restore_free(db, user))


@router.post("/streak-save/stars-invoice", response_model=StarsInvoiceCreateOut)
async def stars_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await loyalty_service.stars_order(db, user))
