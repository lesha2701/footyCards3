from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.wheel import WheelSpinResultOut, WheelStatusOut
from app.services import wheel_service

router = APIRouter(prefix="/wheel", tags=["wheel"])


@router.get("/status", response_model=WheelStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.get_status(db, user)


@router.post("/spin/free", response_model=WheelSpinResultOut)
async def spin_free(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_free(db, user)


@router.post("/spin/coins", response_model=WheelSpinResultOut)
async def spin_paid_coins(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await wheel_service.spin_paid_coins(db, user)
