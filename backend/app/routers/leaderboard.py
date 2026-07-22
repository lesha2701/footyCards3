from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.game import MemoryLeaderboardEntry
from app.schemas.match import ArenaLeaderboardEntry
from app.services import match_service, memory_game_service

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/arena", response_model=list[ArenaLeaderboardEntry])
async def leaderboard_arena(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await match_service.arena_leaderboard(db)


@router.get("/memory", response_model=list[MemoryLeaderboardEntry])
async def leaderboard_memory(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await memory_game_service.leaderboard(db)
