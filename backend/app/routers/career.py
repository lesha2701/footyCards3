from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.career import (
    CareerCreateIn,
    CareerInviteResponseIn,
    CareerLineupIn,
    CareerMatchEventsOut,
    CareerViewOut,
)
from app.services import career_service

router = APIRouter(prefix="/career", tags=["career"])


async def _view(db: AsyncSession, user: User) -> dict:
    view = await career_service.get_view(db, user)
    view["invite"] = await career_service.pending_invite(db, user.id)
    return view


@router.get("", response_model=CareerViewOut)
async def get_career(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The current season (rounds whose time has come are played first)."""
    return await _view(db, user)


@router.post("/seasons", response_model=CareerViewOut)
async def create_season(payload: CareerCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"career_create:{user.id}", max_calls=5, window_seconds=60)
    await career_service.create_season(db, user, payload.difficulty, payload.friend_id)
    return await _view(db, user)


@router.post("/seasons/{season_id}/invite", response_model=CareerViewOut)
async def respond_invite(
    season_id: int, payload: CareerInviteResponseIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await career_service.respond_invite(db, user, season_id, payload.accept)
    return await _view(db, user)


@router.post("/seasons/{season_id}/start", response_model=CareerViewOut)
async def start_without_friend(season_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.start_without_friend(db, user, season_id)
    return await _view(db, user)


@router.put("/lineup", response_model=CareerViewOut)
async def set_lineup(payload: CareerLineupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.set_lineup(db, user, payload.slots, payload.formation, payload.mentality, payload.playstyle)
    return await _view(db, user)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.leave_season(db, user)


@router.get("/seasons/{season_id}/rounds/{round_index}/matches/{match_index}", response_model=CareerMatchEventsOut)
async def match_events(
    season_id: int, round_index: int, match_index: int,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await career_service.match_events(db, user, season_id, round_index, match_index)
