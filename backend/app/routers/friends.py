from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.career import (
    FriendFeedItemOut,
    FriendRelationOut,
    FriendRequestIn,
    FriendRequestResultOut,
    FriendsOut,
)
from app.services import friend_service

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=FriendsOut)
async def list_friends(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await friend_service.list_friends(db, user)


@router.get("/feed", response_model=list[FriendFeedItemOut])
async def friends_feed(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Friends' notable activity over the last 7 days."""
    return await friend_service.feed(db, user)


@router.get("/relation/{user_id}", response_model=FriendRelationOut)
async def relation(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return {"relation": await friend_service.relation(db, user.id, user_id)}


@router.post("/requests", response_model=FriendRequestResultOut)
async def send_request(payload: FriendRequestIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"friend_request:{user.id}", max_calls=20, window_seconds=3600)
    return {"status": await friend_service.send_request(db, user, payload.user_id)}


@router.post("/requests/{request_id}/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await friend_service.respond(db, user, request_id, accept=True)


@router.post("/requests/{request_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await friend_service.respond(db, user, request_id, accept=False)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await friend_service.remove(db, user, user_id)
