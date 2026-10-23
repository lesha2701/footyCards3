from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.my_player import LifestyleCatalogOut, LifestylePublicOut
from app.services import lifestyle_service

router = APIRouter(prefix="/lifestyle", tags=["lifestyle"])


@router.get("", response_model=LifestyleCatalogOut)
async def get_catalog(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await lifestyle_service.catalog(db, user)


@router.post("/{item_id}/buy", response_model=LifestyleCatalogOut)
async def buy_item(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"lifestyle_buy:{user.id}", max_calls=20, window_seconds=60)
    return await lifestyle_service.buy_with_coins(db, user, item_id)


@router.post("/income/claim", response_model=LifestyleCatalogOut)
async def claim_income(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Collects the weekly income of the player's items."""
    await check_rate_limit(f"lifestyle_income:{user.id}", max_calls=10, window_seconds=60)
    return await lifestyle_service.claim_income(db, user)


@router.get("/users/{user_id}", response_model=LifestylePublicOut)
async def get_public(user_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await lifestyle_service.public_view(db, user_id)
