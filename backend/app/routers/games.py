from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.game import (
    MemoryClaimOut,
    MemoryLeaderboardEntry,
    MemoryStartOut,
    MemorySubmitOut,
    MemorySubmitRequest,
)
from app.services import memory_game_service

router = APIRouter(prefix="/games", tags=["games"])


@router.post("/memory/start", response_model=MemoryStartOut)
async def memory_start(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"memory_start:{user.id}", max_calls=20, window_seconds=60)
    return await memory_game_service.start_session(db, user)


@router.post("/memory/{session_id}/submit", response_model=MemorySubmitOut)
async def memory_submit(
    session_id: int,
    payload: MemorySubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await memory_game_service.submit_round(db, user, session_id, payload.answer)


@router.post("/memory/{session_id}/end", response_model=MemorySubmitOut)
async def memory_end(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await memory_game_service.end_session(db, user, session_id)


@router.post("/memory/{session_id}/claim", response_model=MemoryClaimOut)
async def memory_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await memory_game_service.claim_reward(db, user, session_id)


@router.get("/memory/leaderboard", response_model=list[MemoryLeaderboardEntry])
async def memory_leaderboard(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await memory_game_service.leaderboard(db)
