from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.services import stars_patron_service

router = APIRouter(prefix="/stars-patron", tags=["stars-patron"])


class PatronLetterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    created_at: datetime


@router.get("/letters", response_model=list[PatronLetterOut])
async def letters(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stars_patron_service.unseen_letters(db, user)


@router.post("/letters/{letter_id}/seen", status_code=204)
async def seen(letter_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await stars_patron_service.mark_letter_seen(db, user, letter_id)
