from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.user import User
from app.schemas.collection import AlbumCollectionDetailOut, AlbumOverviewOut, CollectionFilterParams, UserCardListItem
from app.schemas.gift import GiftShelfOut
from app.schemas.profile import ProfilePublicOut, ProfileSocialOut
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


@router.get("/{user_id}/album", response_model=AlbumOverviewOut)
async def public_album(
    user_id: int, search: Optional[str] = Query(default=None, max_length=64),
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user),
):
    """Another player's album, read-only — to leaf through and find a trade."""
    from app.services.collection_service import get_album_overview

    await get_public_user(db, user_id)
    return await get_album_overview(db, user_id, search)


@router.get("/{user_id}/album/{collection_id}", response_model=AlbumCollectionDetailOut)
async def public_album_page(
    user_id: int, collection_id: int, search: Optional[str] = Query(default=None, max_length=64),
    db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user),
):
    from app.services.collection_service import get_album_collection_detail

    await get_public_user(db, user_id)
    return await get_album_collection_detail(db, user_id, collection_id, search)


async def get_public_user(db: AsyncSession, user_id: int) -> User:
    from app.core.exceptions import NotFoundError

    target = await db.get(User, user_id)
    if target is None or target.is_banned:
        raise NotFoundError("User not found")
    return target


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


@router.get("/{user_id}/gift-shelf", response_model=GiftShelfOut)
async def user_gift_shelf(user_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    from app.services.gift_service import gift_shelf

    return await gift_shelf(db, user_id)


@router.get("/{user_id}/social", response_model=ProfileSocialOut)
async def user_social(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services import profile_social_service

    return await profile_social_service.social(db, user, user_id)


@router.post("/{user_id}/respect", response_model=ProfileSocialOut)
async def user_respect(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.core.rate_limit import check_rate_limit
    from app.services import profile_social_service

    await check_rate_limit(f"respect:{user.id}", max_calls=30, window_seconds=60)
    return await profile_social_service.give_respect(db, user, user_id)
