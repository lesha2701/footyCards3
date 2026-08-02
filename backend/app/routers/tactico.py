from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.tactico import (
    TacticoBotMatchRequest,
    TacticoChallengeRequest,
    TacticoMatchOut,
    TacticoRoundSubmitRequest,
    TacticoSquadOut,
    TacticoSquadSetRequest,
    TacticoStatsOut,
)
from app.services import tactico_service

router = APIRouter(prefix="/tactico", tags=["tactico"])


@router.get("/stats", response_model=TacticoStatsOut)
async def get_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.get_stats(db, user)


@router.get("/squad", response_model=TacticoSquadOut)
async def get_squad(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.get_squad(db, user)


@router.put("/squad", response_model=TacticoSquadOut)
async def set_squad(
    payload: TacticoSquadSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await tactico_service.set_squad(db, user, payload.user_card_ids)


@router.post("/matches/bot", response_model=TacticoMatchOut)
async def create_bot_match(
    payload: TacticoBotMatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"tactico_bot_match:{user.id}", max_calls=15, window_seconds=60)
    return await tactico_service.create_bot_match(db, user, payload.difficulty)


@router.post("/matches/challenge", response_model=TacticoMatchOut)
async def create_challenge(
    payload: TacticoChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"tactico_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await tactico_service.create_challenge(db, user, payload.receiver_id)


@router.post("/matches/{match_id}/accept", response_model=TacticoMatchOut)
async def accept_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.accept_challenge(db, user, match_id)


@router.post("/matches/{match_id}/decline", response_model=TacticoMatchOut)
async def decline_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.decline_challenge(db, user, match_id)


@router.post("/matches/{match_id}/cancel", response_model=TacticoMatchOut)
async def cancel_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.cancel_challenge(db, user, match_id)


@router.post("/matches/{match_id}/forfeit", response_model=TacticoMatchOut)
async def forfeit_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.forfeit_match(db, user, match_id)


@router.post("/matches/{match_id}/rounds", response_model=TacticoMatchOut)
async def submit_round(
    match_id: int,
    payload: TacticoRoundSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await tactico_service.submit_round(db, user, match_id, payload.user_card_id)


@router.get("/matches", response_model=list[TacticoMatchOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.list_matches(db, user)


@router.get("/matches/{match_id}", response_model=TacticoMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await tactico_service.get_match(db, user, match_id)
