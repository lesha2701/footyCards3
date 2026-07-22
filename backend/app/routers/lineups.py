from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.lineup import LineupOut, LineupSetRequest
from app.services.lineup_service import get_active_lineup, set_lineup

router = APIRouter(prefix="/lineups", tags=["lineups"])


@router.get("/active", response_model=LineupOut)
async def read_active_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_active_lineup(db, user)


@router.put("/active", response_model=LineupOut)
async def update_active_lineup(
    payload: LineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup(db, user, payload)
