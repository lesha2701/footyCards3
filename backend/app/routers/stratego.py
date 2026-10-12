from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.stratego import (
    StrategoChallengeRequest,
    StrategoInfoOut,
    StrategoBotMatchRequest,
    StrategoMatchOut,
    StrategoNoteRequest,
    StrategoPuzzleOut,
    StrategoMoveRequest,
    StrategoOpenChallengePreviewOut,
    StrategoOpenChallengeRequest,
    StrategoSearchStatusOut,
    StrategoSquadOut,
    StrategoSquadSetRequest,
    StrategoStatsOut,
)
from app.services import stratego_service

router = APIRouter(prefix="/stratego", tags=["stratego"])


@router.get("/info", response_model=StrategoInfoOut)
async def get_info(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.get_info(db, user)


@router.get("/stats", response_model=StrategoStatsOut)
async def get_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.get_stats(db, user)


@router.get("/squad", response_model=StrategoSquadOut)
async def get_squad(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.get_squad(db, user)


@router.put("/squad", response_model=StrategoSquadOut)
async def set_squad(
    payload: StrategoSquadSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await stratego_service.set_squad(db, user, payload.cards, payload.layout)


@router.post("/matches/bot", response_model=StrategoMatchOut)
async def create_bot_match(
    payload: StrategoBotMatchRequest | None = None,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"stratego_bot_match:{user.id}", max_calls=15, window_seconds=60)
    return await stratego_service.create_bot_match(db, user, (payload or StrategoBotMatchRequest()).difficulty)


@router.get("/puzzle", response_model=StrategoPuzzleOut)
async def get_puzzle(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.get_puzzle(db, user)


@router.post("/puzzle/start", response_model=StrategoMatchOut)
async def start_puzzle(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"stratego_puzzle:{user.id}", max_calls=20, window_seconds=60)
    return await stratego_service.start_puzzle(db, user)


@router.post("/tutorial/start", response_model=StrategoMatchOut)
async def start_tutorial(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"stratego_tutorial:{user.id}", max_calls=20, window_seconds=60)
    return await stratego_service.start_tutorial(db, user)


@router.post("/matches/{match_id}/notes", response_model=StrategoMatchOut)
async def set_note(
    match_id: int, payload: StrategoNoteRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await stratego_service.set_note(db, user, match_id, payload.piece_id, payload.tag)


@router.post("/matches/challenge", response_model=StrategoMatchOut)
async def create_challenge(
    payload: StrategoChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"stratego_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await stratego_service.create_challenge(db, user, payload.receiver_id)


@router.post("/matches/open-challenge", response_model=StrategoMatchOut)
async def create_open_challenge(
    payload: StrategoOpenChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"stratego_open_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await stratego_service.create_open_challenge(db, user, payload.stake_coins)


@router.get("/matches/open/{match_id}", response_model=StrategoOpenChallengePreviewOut)
async def preview_open_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.preview_open_challenge(db, user, match_id)


@router.post("/matches/open/{match_id}/accept", response_model=StrategoMatchOut)
async def accept_open_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.accept_open_challenge(db, user, match_id)


@router.post("/matches/{match_id}/accept", response_model=StrategoMatchOut)
async def accept_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.accept_challenge(db, user, match_id)


@router.post("/matches/{match_id}/decline", response_model=StrategoMatchOut)
async def decline_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.decline_challenge(db, user, match_id)


@router.post("/matches/{match_id}/cancel", response_model=StrategoMatchOut)
async def cancel_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.cancel_challenge(db, user, match_id)


@router.post("/matches/{match_id}/forfeit", response_model=StrategoMatchOut)
async def forfeit_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.forfeit_match(db, user, match_id)


@router.post("/matches/{match_id}/move", response_model=StrategoMatchOut)
async def submit_move(
    match_id: int, payload: StrategoMoveRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"stratego_move:{user.id}", max_calls=120, window_seconds=60)
    return await stratego_service.submit_move(
        db, user, match_id, payload.from_row, payload.from_col, payload.to_row, payload.to_col
    )


@router.get("/matches", response_model=list[StrategoMatchOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.list_matches(db, user)


@router.get("/matches/{match_id}", response_model=StrategoMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await stratego_service.get_match(db, user, match_id)


@router.post("/matchmaking/search", response_model=StrategoSearchStatusOut)
async def start_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"stratego_search:{user.id}", max_calls=10, window_seconds=60)
    entry = await stratego_service.start_search(db, user)
    return StrategoSearchStatusOut(status="searching", match_id=None, created_at=entry.created_at)


@router.get("/matchmaking/status", response_model=StrategoSearchStatusOut)
async def get_search_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    status, match_id = await stratego_service.get_search_status(db, user)
    return StrategoSearchStatusOut(status=status, match_id=match_id, created_at=None)


@router.post("/matchmaking/cancel", status_code=204)
async def cancel_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await stratego_service.cancel_search(db, user)
