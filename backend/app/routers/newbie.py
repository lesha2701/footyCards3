from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.newbie import NewbieClaimOut, NewbieOut
from app.schemas.pack import PackOpenResult
from app.services import newbie_service

router = APIRouter(prefix="/newbie", tags=["newbie"])


@router.get("", response_model=NewbieOut)
async def get_state(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await newbie_service.get_state(db, user)


@router.post("/first-pack", response_model=PackOpenResult)
async def first_pack(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await newbie_service.open_first_pack(db, user)


@router.post("/squad-pack", response_model=PackOpenResult)
async def squad_pack(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await newbie_service.open_squad_pack(db, user)


@router.post("/arena-card", response_model=PackOpenResult)
async def arena_card(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await newbie_service.open_arena_card(db, user)


@router.post("/claim/{code}", response_model=NewbieClaimOut)
async def claim(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await newbie_service.claim(db, user, code)
