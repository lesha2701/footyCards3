from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.career import CareerClub
from app.models.player import Player
from app.models.user import User
from app.services import career_league_service, career_tactics_service
from app.services.admin_log_service import log_action
from app.services.club_formation_service import CLUB_FORMATIONS
from app.services.game_config_service import get_config

router = APIRouter(prefix="/admin/career", tags=["admin"], dependencies=[Depends(get_current_admin)])


class CareerClubIn(BaseModel):
    name: str = Field(min_length=2, max_length=64)
    division: int = Field(ge=1, le=10)
    pool_club: Optional[str] = Field(default=None, max_length=128)
    rating_offset: int = Field(default=0, ge=-15, le=15)
    formation: Optional[str] = None
    preset: Optional[str] = None
    is_active: bool = True


class CareerClubBuildIn(BaseModel):
    # True: drop real/generated clubs and rebuild from the card pool.
    replace: bool = False


def _validate(payload: CareerClubIn, division_count: int) -> None:
    if payload.division > division_count:
        raise ConflictError(f"Дивизионов всего {division_count}")
    if payload.formation and payload.formation not in CLUB_FORMATIONS:
        raise ConflictError("Неизвестная схема")
    if payload.preset and payload.preset not in career_tactics_service.PRESETS:
        raise ConflictError("Неизвестная тактика")


async def _out(db: AsyncSession) -> dict:
    clubs = (await db.execute(select(CareerClub).order_by(CareerClub.division, CareerClub.name))).scalars().all()
    pool = dict((await db.execute(
        select(Player.club, func.count()).where(Player.is_active.is_(True)).group_by(Player.club)
    )).all())
    return {"clubs": [
        {"id": c.id, "name": c.name, "division": c.division, "source": c.source, "pool_club": c.pool_club,
         "pool_players": int(pool.get(c.pool_club, 0)) if c.pool_club else 0, "rating_offset": c.rating_offset,
         "formation": c.formation, "preset": c.preset, "is_active": c.is_active}
        for c in clubs
    ]}


@router.get("/clubs")
async def list_clubs(db: AsyncSession = Depends(get_db)):
    return await _out(db)


@router.post("/clubs/build")
async def build_clubs(payload: CareerClubBuildIn, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    """Forms the division catalog from the real clubs of the card pool and
    fills the rest with generated clubs (clubs added by hand are kept)."""
    config = await get_config(db)
    result = await career_league_service.build_catalog(db, config, replace=payload.replace)
    await log_action(db, admin.id, "career_clubs_build", "career_club", new_value={"replace": payload.replace, **result})
    await db.commit()
    return await _out(db)


@router.post("/clubs")
async def create_club(payload: CareerClubIn, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    config = await get_config(db)
    _validate(payload, career_league_service.division_count(config))
    club = CareerClub(**payload.model_dump(), source="admin")
    db.add(club)
    await db.flush()
    await log_action(db, admin.id, "career_club_create", "career_club", entity_id=club.id, new_value={"name": club.name})
    await db.commit()
    return await _out(db)


@router.put("/clubs/{club_id}")
async def update_club(
    club_id: int, payload: CareerClubIn, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    config = await get_config(db)
    _validate(payload, career_league_service.division_count(config))
    club = await db.get(CareerClub, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    for key, value in payload.model_dump().items():
        setattr(club, key, value)
    await log_action(db, admin.id, "career_club_update", "career_club", entity_id=club.id, new_value=payload.model_dump())
    await db.commit()
    return await _out(db)
