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
