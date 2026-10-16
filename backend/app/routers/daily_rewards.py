from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.monetization import CalendarCatchupIn, CalendarClaimOut, CalendarOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import daily_reward_service, shop_product_service

router = APIRouter(prefix="/daily-rewards", tags=["daily-rewards"])


@router.get("/calendar", response_model=CalendarOut)
async def get_calendar(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await daily_reward_service.get_calendar(db, user)


@router.post("/claim", response_model=CalendarClaimOut)
async def claim_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await daily_reward_service.claim_daily_reward(db, user)


@router.post("/catch-up", response_model=CalendarClaimOut)
async def catch_up(payload: CalendarCatchupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await daily_reward_service.catch_up_with_coins(db, user, payload.date)


@router.post("/catch-up/stars-invoice", response_model=StarsInvoiceCreateOut)
async def catch_up_stars(
    payload: CalendarCatchupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    order = await daily_reward_service.stars_order(db, user, payload.date)
    return await shop_product_service.create_invoice(db, user, *order)
