from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.free_pack import FreePackClaimOut, FreePackStatusOut
from app.services import free_pack_service

router = APIRouter(prefix="/free-pack", tags=["free-pack"])


@router.get("/status", response_model=FreePackStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_pack_service.get_status(db, user)


@router.post("/claim", response_model=FreePackClaimOut)
async def claim(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_pack_service.claim_free_pack(db, user)
