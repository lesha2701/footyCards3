from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.halloween import HalloweenBuyOut, HalloweenBuyRequest, HalloweenDoorResultOut, HalloweenStateOut
from app.services import halloween_service

router = APIRouter(prefix="/halloween", tags=["halloween"])


@router.get("", response_model=HalloweenStateOut)
async def get_state(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await halloween_service.get_state(db, user)


@router.post("/shop/{item_code}", response_model=HalloweenBuyOut)
async def buy(item_code: str, payload: HalloweenBuyRequest, db: AsyncSession = Depends(get_db),
              user: User = Depends(get_current_user)):
    await check_rate_limit(f"halloween_shop:{user.id}", max_calls=20, window_seconds=60)
    return await halloween_service.buy(db, user, item_code, payload.idempotency_key)


@router.post("/doors/{door}", response_model=HalloweenDoorResultOut)
async def open_door(door: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"halloween_door:{user.id}", max_calls=10, window_seconds=60)
    return await halloween_service.open_door(db, user, door)
