from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.player_career import PlayerCareerContractIn, PlayerCareerViewOut
from app.services import player_career_service

router = APIRouter(prefix="/player-career", tags=["player-career"])


@router.get("", response_model=PlayerCareerViewOut)
async def get_player_career(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Clubs, contract, the current/last season (due rounds are played first)."""
    return await player_career_service.get_view(db, user)


@router.post("/contract", response_model=PlayerCareerViewOut)
async def sign_contract(payload: PlayerCareerContractIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"player_career_contract:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_service.sign_contract(db, user, payload.club_key)


@router.post("/seasons", response_model=PlayerCareerViewOut)
async def start_season(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"player_career_season:{user.id}", max_calls=5, window_seconds=60)
    return await player_career_service.start_season(db, user)


@router.post("/leave", response_model=PlayerCareerViewOut)
async def leave_season(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_career_service.leave_season(db, user)
