from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.league import LeagueStatusOut, LeagueTierPublicOut
from app.services import league_service

router = APIRouter(prefix="/leagues", tags=["leagues"])


@router.get("", response_model=list[LeagueTierPublicOut])
async def list_leagues(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await league_service.list_tiers(db)


@router.get("/status", response_model=LeagueStatusOut)
async def league_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await league_service.get_league_status(db, user)
