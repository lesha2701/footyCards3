from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.penalty_match import (
    PenaltyAcceptRequest,
    PenaltyChallengeRequest,
    PenaltyMatchOut,
    PenaltyPickRequest,
    PenaltySearchRequest,
    PenaltySearchStatusOut,
)
from app.services import penalty_match_service

router = APIRouter(prefix="/games/penalty", tags=["penalty"])


@router.post("/challenges", response_model=PenaltyMatchOut)
async def create_challenge(
    payload: PenaltyChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"penalty_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await penalty_match_service.create_challenge(db, user, payload.opponent_user_id, payload.user_card_id)


@router.post("/challenges/{match_id}/accept", response_model=PenaltyMatchOut)
async def accept_challenge(
    match_id: int, payload: PenaltyAcceptRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await penalty_match_service.accept_challenge(db, user, match_id, payload.user_card_id)


@router.post("/challenges/{match_id}/decline", response_model=PenaltyMatchOut)
async def decline_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.decline_challenge(db, user, match_id)


@router.post("/challenges/{match_id}/cancel", response_model=PenaltyMatchOut)
async def cancel_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.cancel_challenge(db, user, match_id)


@router.post("/matches/{match_id}/pick", response_model=PenaltyMatchOut)
async def submit_pick(
    match_id: int, payload: PenaltyPickRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await penalty_match_service.submit_pick(db, user, match_id, payload.zone)


@router.post("/matches/{match_id}/forfeit", response_model=PenaltyMatchOut)
async def forfeit_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.forfeit_match(db, user, match_id)


@router.get("/matches", response_model=list[PenaltyMatchOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.list_matches(db, user)


@router.get("/matches/{match_id}", response_model=PenaltyMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_match_service.get_match(db, user, match_id)


@router.post("/matchmaking/search", response_model=PenaltySearchStatusOut)
async def start_search(
    payload: PenaltySearchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"penalty_search:{user.id}", max_calls=10, window_seconds=60)
    entry = await penalty_match_service.start_search(db, user, payload.user_card_id)
    return PenaltySearchStatusOut(status="searching", match_id=None, created_at=entry.created_at)


@router.get("/matchmaking/status", response_model=PenaltySearchStatusOut)
async def get_search_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    status, match_id = await penalty_match_service.get_search_status(db, user)
    return PenaltySearchStatusOut(status=status, match_id=match_id, created_at=None)


@router.post("/matchmaking/cancel", status_code=204)
async def cancel_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await penalty_match_service.cancel_search(db, user)
