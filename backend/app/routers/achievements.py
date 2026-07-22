from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.achievement_service import list_with_progress

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("")
async def get_my_achievements(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_with_progress(db, user)
