from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.fan_battle import FanBattleStateOut, FanClaimOut
from app.services import fan_battle_service

router = APIRouter(prefix="/fans", tags=["fan-battle"])


@router.get("", response_model=FanBattleStateOut)
async def get_state(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await fan_battle_service.get_state(db, user)


@router.post("/side/{side}", response_model=FanBattleStateOut)
async def join(side: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"fans_join:{user.id}", max_calls=10, window_seconds=60)
    return await fan_battle_service.join(db, user, side)


@router.post("/claim", response_model=FanClaimOut)
async def claim(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"fans_claim:{user.id}", max_calls=10, window_seconds=60)
    return await fan_battle_service.claim(db, user)
