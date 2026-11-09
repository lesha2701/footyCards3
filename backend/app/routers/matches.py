from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.match import (
    ArenaDefenseItemOut,
    ArenaLeaderboardEntry,
    ArenaPreviewOut,
    ArenaStatsOut,
    MatchActionRequest,
    MatchHistoryItemOut,
    MatchOut,
    StartMatchRequest,
)
from app.services import match_service

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("/opponent", response_model=ArenaPreviewOut)
async def opponent_preview(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"arena_opponent:{user.id}", max_calls=30, window_seconds=60)
    return await match_service.preview_opponent(db, user)


@router.post("/play", response_model=MatchOut)
async def play_match(
    payload: StartMatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"play_match:{user.id}", max_calls=15, window_seconds=60)
    return await match_service.start_match(db, user, payload)


@router.post("/{match_id}/act", response_model=MatchOut)
async def act(
    match_id: int, payload: MatchActionRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await match_service.resolve_action(db, user, match_id, payload)


@router.post("/{match_id}/forfeit", response_model=MatchOut)
async def forfeit(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.forfeit_match(db, user, match_id)


@router.get("/active", response_model=Optional[MatchOut])
async def get_active_match(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.active_match(db, user)


@router.get("/defense-log", response_model=list[ArenaDefenseItemOut])
async def get_defense_log(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.defense_log(db, user)


@router.post("/defense-log/seen", status_code=204)
async def mark_defense_seen(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await match_service.mark_defense_seen(db, user)


@router.post("/{match_id}/revenge", response_model=ArenaPreviewOut)
async def revenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.take_revenge(db, user, match_id)


@router.get("/history", response_model=list[MatchOut])
async def get_match_history(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.match_history(db, user)


@router.get("/recent", response_model=list[MatchHistoryItemOut])
async def get_recent_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.recent_matches(db, user)


@router.get("/stats", response_model=ArenaStatsOut)
async def get_arena_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.arena_stats(db, user)


@router.get("/leaderboard", response_model=list[ArenaLeaderboardEntry])
async def get_arena_leaderboard(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await match_service.arena_leaderboard(db)


@router.get("/{match_id}", response_model=MatchOut)
async def get_match_detail(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.get_match(db, user, match_id)
