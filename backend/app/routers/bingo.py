from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.bingo import BingoClaimResult, BingoCurrentOut
from app.services.bingo_service import claim_reward, get_current_week_out

router = APIRouter(prefix="/bingo", tags=["bingo"])


@router.get("/current", response_model=BingoCurrentOut)
async def get_current_bingo(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_current_week_out(db, user)


@router.post("/claim", response_model=BingoClaimResult)
async def claim_current_bingo_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await claim_reward(db, user)
