from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubSummaryOut
from app.services import club_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubSummaryOut])
async def list_clubs(
    search: Optional[str] = Query(default=None), db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    return await club_service.list_clubs(db, search)


@router.get("/me", response_model=ClubDetailOut)
async def get_my_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_my_club_detail(db, user)


@router.get("/{club_id}", response_model=ClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_club_detail(db, club_id, requester_user_id=user.id)


@router.post("", response_model=ClubDetailOut)
async def create_club(
    payload: ClubCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_service.create_club(db, user, payload)
