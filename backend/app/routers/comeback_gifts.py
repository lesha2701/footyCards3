from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import comeback_gift_service

router = APIRouter(prefix="/comeback-gifts", tags=["comeback-gifts"])


class ComebackGiftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    days_away: int
    rewards: dict


@router.get("/unseen", response_model=list[ComebackGiftOut])
async def unseen(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await comeback_gift_service.unseen(db, user)


@router.post("/{gift_id}/seen", status_code=204)
async def seen(gift_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await comeback_gift_service.mark_seen(db, user, gift_id)
