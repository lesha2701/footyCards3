from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.magnate import (
    MagnateActionRequest,
    MagnateInfoOut,
    MagnateMatchBriefOut,
    MagnateMatchOut,
    MagnateRoomPreviewOut,
)
from app.services import magnate_service

router = APIRouter(prefix="/magnate", tags=["magnate"])


@router.get("/info", response_model=MagnateInfoOut)
async def get_info(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.get_info(db, user)


@router.get("/matches", response_model=list[MagnateMatchBriefOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.list_matches(db, user)


@router.post("/matches/bot", response_model=MagnateMatchOut)
async def create_bot_match(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magnate_create:{user.id}", max_calls=10, window_seconds=60)
    return await magnate_service.create_bot_match(db, user)


@router.post("/lobby/join", response_model=MagnateMatchOut)
async def join_public_lobby(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magnate_create:{user.id}", max_calls=10, window_seconds=60)
    return await magnate_service.join_public_lobby(db, user)


@router.post("/rooms", response_model=MagnateMatchOut)
async def create_room(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magnate_create:{user.id}", max_calls=10, window_seconds=60)
    return await magnate_service.create_room(db, user)


@router.get("/rooms/{code}", response_model=MagnateRoomPreviewOut)
async def preview_room(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.preview_room(db, user, code)


@router.post("/rooms/{code}/join", response_model=MagnateMatchOut)
async def join_room(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"magnate_create:{user.id}", max_calls=10, window_seconds=60)
    return await magnate_service.join_room(db, user, code)


@router.get("/matches/{match_id}", response_model=MagnateMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.get_match(db, user, match_id)


@router.post("/matches/{match_id}/start", response_model=MagnateMatchOut)
async def start_room(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.start_room(db, user, match_id)


@router.post("/matches/{match_id}/leave", response_model=Optional[MagnateMatchOut])
async def leave_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await magnate_service.leave_match(db, user, match_id)


@router.post("/matches/{match_id}/action", response_model=MagnateMatchOut)
async def act(
    match_id: int, payload: MagnateActionRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"magnate_action:{user.id}", max_calls=120, window_seconds=60)
    return await magnate_service.act(db, user, match_id, payload.action, payload.cell, payload.version)
