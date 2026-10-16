from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.monetization import CosmeticIn, CosmeticOut, SeasonAdminOut, SeasonIn
from app.services import cosmetic_service, season_pass_service
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("/cosmetics", response_model=list[CosmeticOut])
async def list_cosmetics(db: AsyncSession = Depends(get_db)):
    return await cosmetic_service.admin_list(db)


@router.post("/cosmetics", response_model=CosmeticOut)
async def create_cosmetic(
    payload: CosmeticIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await cosmetic_service.admin_create(db, payload)
    await log_action(db, admin.id, "create_cosmetic", "cosmetic", out.id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/cosmetics/{cosmetic_id}", response_model=CosmeticOut)
async def update_cosmetic(
    cosmetic_id: int, payload: CosmeticIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await cosmetic_service.admin_update(db, cosmetic_id, payload)
    await log_action(db, admin.id, "update_cosmetic", "cosmetic", cosmetic_id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.get("/seasons", response_model=list[SeasonAdminOut])
async def list_seasons(db: AsyncSession = Depends(get_db)):
    return await season_pass_service.admin_list(db)


@router.post("/seasons", response_model=SeasonAdminOut)
async def create_season(
    payload: SeasonIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await season_pass_service.admin_create(db, payload)
    await log_action(db, admin.id, "create_season", "season", out.id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/seasons/{season_id}", response_model=SeasonAdminOut)
async def update_season(
    season_id: int, payload: SeasonIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await season_pass_service.admin_update(db, season_id, payload)
    await log_action(db, admin.id, "update_season", "season", season_id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out
