from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.game import (
    FreeKickClaimOut,
    FreeKickKickOut,
    FreeKickKickRequest,
    FreeKickStartOut,
    FreeKickStartRequest,
    MemoryClaimOut,
    MemoryLeaderboardEntry,
    MemoryStartOut,
    MemorySubmitOut,
    MemorySubmitRequest,
    PenaltyClaimOut,
    PenaltyKickOut,
    PenaltyKickRequest,
    PenaltyStartOut,
    PenaltyStartRequest,
    SaboteurClaimOut,
    SaboteurRevealOut,
    SaboteurRevealRequest,
    SaboteurStartOut,
    SaboteurStartRequest,
)
from app.services import free_kick_service, memory_game_service, penalty_service, saboteur_service

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


# --- Saboteur ---

@router.post("/saboteur/start", response_model=SaboteurStartOut)
async def saboteur_start(payload: SaboteurStartRequest = SaboteurStartRequest(), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"saboteur_start:{user.id}", max_calls=20, window_seconds=60)
    return await saboteur_service.start_session(db, user, payload.bomb_count)


@router.post("/saboteur/{session_id}/reveal", response_model=SaboteurRevealOut)
async def saboteur_reveal(session_id: int, payload: SaboteurRevealRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.reveal_cell(db, user, session_id, payload.cell_index)


@router.post("/saboteur/{session_id}/end", response_model=SaboteurRevealOut)
async def saboteur_end(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.end_session(db, user, session_id)


@router.post("/saboteur/{session_id}/claim", response_model=SaboteurClaimOut)
async def saboteur_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await saboteur_service.claim_reward(db, user, session_id)


# --- Penalty ---

@router.post("/penalty/start", response_model=PenaltyStartOut)
async def penalty_start(payload: PenaltyStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"penalty_start:{user.id}", max_calls=20, window_seconds=60)
    return await penalty_service.start_session(db, user, payload.user_card_id)


@router.post("/penalty/{session_id}/kick", response_model=PenaltyKickOut)
async def penalty_kick(session_id: int, payload: PenaltyKickRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.resolve_kick(db, user, session_id, payload.direction)


@router.post("/penalty/{session_id}/claim", response_model=PenaltyClaimOut)
async def penalty_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await penalty_service.claim_reward(db, user, session_id)


# --- Free Kick ---

@router.post("/free-kick/start", response_model=FreeKickStartOut)
async def free_kick_start(payload: FreeKickStartRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"free_kick_start:{user.id}", max_calls=20, window_seconds=60)
    return await free_kick_service.start_session(db, user, payload.user_card_id)


@router.post("/free-kick/{session_id}/kick", response_model=FreeKickKickOut)
async def free_kick_kick(session_id: int, payload: FreeKickKickRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_kick_service.resolve_kick(db, user, session_id, payload.elapsed_ms)


@router.post("/free-kick/{session_id}/claim", response_model=FreeKickClaimOut)
async def free_kick_claim(session_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await free_kick_service.claim_reward(db, user, session_id)
