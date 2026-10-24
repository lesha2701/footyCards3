from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.weekly_top import WeeklyTopAwardOut, WeeklyTopInfoOut, WeeklyTopSeenIn
from app.services import weekly_top_service

router = APIRouter(prefix="/weekly-top", tags=["weekly-top"])


@router.get("/awards", response_model=list[WeeklyTopAwardOut])
async def get_awards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The player's unseen «Топ недели» places (one popup each). Settles the
    closed week first if the bot hasn't yet."""
    return await weekly_top_service.pending(db, user)


@router.post("/awards/seen")
async def mark_seen(body: WeeklyTopSeenIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return {"seen": await weekly_top_service.mark_seen(db, user, body.ids)}


@router.get("/info", response_model=WeeklyTopInfoOut)
async def get_info(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await weekly_top_service.info(db)
