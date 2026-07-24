from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.user import User
from app.schemas.collection import CollectionFilterParams, UserCardListItem
from app.schemas.profile import ProfilePublicOut
from app.schemas.user import UserPublicOut
from app.services.collection_service import list_user_cards
from app.services.profile_service import get_public_profile, search_users

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserPublicOut])
async def search(
    q: str = Query(min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await search_users(db, q, exclude_user_id=user.id)


@router.get("/{user_id}", response_model=ProfilePublicOut)
async def public_profile(user_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await get_public_profile(db, user_id)


@router.get("/{user_id}/collection", response_model=Page[UserCardListItem])
async def public_collection(
    user_id: int,
    filters: CollectionFilterParams = Depends(),
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Public, read-only view of another player's cards — used when building a trade offer."""
    return await list_user_cards(db, user_id, filters, params, exclude_hidden=True)
