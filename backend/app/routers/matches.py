from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.match import ArenaLeaderboardEntry, ArenaStatsOut, MatchOut, StartMatchRequest
from app.services import match_service

router = APIRouter(prefix="/matches", tags=["matches"])


@router.post("/play", response_model=MatchOut)
async def play_match(
    payload: StartMatchRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    check_rate_limit(f"play_match:{user.id}", max_calls=15, window_seconds=60)
    return await match_service.start_match(db, user, payload)


@router.get("/history", response_model=list[MatchOut])
async def get_match_history(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.match_history(db, user)


@router.get("/stats", response_model=ArenaStatsOut)
async def get_arena_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.arena_stats(db, user)


@router.get("/leaderboard", response_model=list[ArenaLeaderboardEntry])
async def get_arena_leaderboard(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await match_service.arena_leaderboard(db)


@router.get("/{match_id}", response_model=MatchOut)
async def get_match_detail(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_service.get_match(db, user, match_id)
