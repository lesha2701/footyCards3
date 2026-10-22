"""«Неделя мини-игры», «Матч дня» and «Клубный рейд» (see their services)."""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin, get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.services import club_raid_service, match_day_auto, match_day_service, weekly_cup_service
from app.services.game_config_service import get_config
from app.config import get_settings
from app.services.admin_log_service import log_action

router = APIRouter(tags=["events"])
admin_router = APIRouter(prefix="/admin/match-day", tags=["admin"])


class PredictionIn(BaseModel):
    home: int = Field(ge=0, le=match_day_service.MAX_GOALS)
    away: int = Field(ge=0, le=match_day_service.MAX_GOALS)


class FixtureIn(BaseModel):
    home: str = Field(min_length=1, max_length=64)
    away: str = Field(min_length=1, max_length=64)
    league: Optional[str] = Field(default=None, max_length=64)
    kickoff_at: datetime


class FixtureUpdate(BaseModel):
    home: Optional[str] = Field(default=None, max_length=64)
    away: Optional[str] = Field(default=None, max_length=64)
    league: Optional[str] = Field(default=None, max_length=64)
    kickoff_at: Optional[datetime] = None
    home_score: Optional[int] = Field(default=None, ge=0, le=match_day_service.MAX_GOALS)
    away_score: Optional[int] = Field(default=None, ge=0, le=match_day_service.MAX_GOALS)
    clear_result: bool = False


@router.get("/weekly-cup")
async def weekly_cup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await weekly_cup_service.get_view(db, user)


@router.post("/weekly-cup/claim")
async def weekly_cup_claim(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await weekly_cup_service.claim(db, user)


@router.get("/match-day")
async def match_day(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_day_service.get_view(db, user)


@router.put("/match-day/{fixture_id}/prediction")
async def match_day_predict(
    fixture_id: int, payload: PredictionIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"match_day_predict:{user.id}", max_calls=30, window_seconds=60)
    return await match_day_service.predict(db, user, fixture_id, payload.home, payload.away)


@router.post("/match-day/{fixture_id}/claim")
async def match_day_claim(fixture_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await match_day_service.claim(db, user, fixture_id)


@router.get("/clubs/me/raid")
async def club_raid(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_raid_service.get_view(db, user)


@router.post("/clubs/me/raid/attack")
async def club_raid_attack(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"club_raid_attack:{user.id}", max_calls=10, window_seconds=60)
    return await club_raid_service.attack(db, user)


@admin_router.get("")
async def admin_fixtures(db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    return await match_day_service.admin_list(db)


@admin_router.post("")
async def admin_create_fixture(payload: FixtureIn, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    await log_action(db, admin.id, "create_match_day", "match_day_fixture", new_value=payload.model_dump(mode="json"))
    return await match_day_service.admin_create(db, payload.home, payload.away, payload.league, payload.kickoff_at)


@admin_router.patch("/{fixture_id}")
async def admin_update_fixture(
    fixture_id: int, payload: FixtureUpdate, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    await log_action(db, admin.id, "update_match_day", "match_day_fixture", fixture_id,
                     new_value=payload.model_dump(mode="json", exclude_unset=True))
    return await match_day_service.admin_update(
        db, fixture_id, payload.home, payload.away, payload.league, payload.kickoff_at,
        payload.home_score, payload.away_score, payload.clear_result,
    )


@admin_router.delete("/{fixture_id}")
async def admin_delete_fixture(fixture_id: int, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    await log_action(db, admin.id, "delete_match_day", "match_day_fixture", fixture_id)
    return await match_day_service.admin_delete(db, fixture_id)


@admin_router.get("/auto")
async def admin_auto_status(db: AsyncSession = Depends(get_db), _admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    return {
        "enabled": bool(config.match_day_enabled and config.match_day_auto_enabled),
        "has_key": bool(get_settings().api_football_key),
        "status": config.match_day_auto_status,
    }


@admin_router.post("/sync")
async def admin_sync(db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    """«Обновить сейчас»: one pass right away, even when the automatic mode is off."""
    await log_action(db, admin.id, "sync_match_day", "match_day_fixture")
    return await match_day_auto.sync(db, force=True)
