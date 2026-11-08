"""Admin «Жители города»: the resident cards catalog (drawn and named by
the admin), their pictures and grants. The numbers (rent per resident,
spare-copy prices, bonus caps) are GameConfig, saved through
/admin/games/config like the rest of the town settings."""
from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.town import TownResident
from app.models.user import User
from app.services import town_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_resident_image, save_resident_image

router = APIRouter(prefix="/admin/town", tags=["admin"], dependencies=[Depends(get_current_admin)])


class ResidentIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    title: Optional[str] = Field(default=None, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    icon: str = Field(default="🧑", max_length=16)
    rarity: str = "common"
    bonus: str = "none"
    bonus_value: int = Field(default=0, ge=0, le=100_000)
    drop_weight: int = Field(default=100, ge=0, le=100_000)
    is_pack_droppable: bool = True
    is_active: bool = True
    sort_order: int = 0


class GrantIn(BaseModel):
    user_id: int


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("/residents")
async def catalog(db: AsyncSession = Depends(get_db)):
    return await town_service.admin_catalog(db)


async def _save(db: AsyncSession, admin: User, request: Request, payload: ResidentIn, row_id=None) -> dict:
    out = await town_service.admin_save(db, payload.model_dump(), row_id)
    await log_action(db, admin.id, f"{'update' if row_id else 'create'}_town_resident", "town_resident", out["id"],
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.post("/residents")
async def create_resident(payload: ResidentIn, request: Request, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, payload)


@router.put("/residents/{row_id}")
async def update_resident(row_id: int, payload: ResidentIn, request: Request, db: AsyncSession = Depends(get_db),
                          admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, payload, row_id)


@router.post("/residents/{row_id}/image")
async def upload_image(row_id: int, request: Request, file: UploadFile = File(...),
                       db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    row = await db.get(TownResident, row_id)
    if row is None:
        raise NotFoundError("Житель не найден")
    old_path = row.image_path
    row.image_path = await save_resident_image(file, row.name)
    delete_resident_image(old_path)
    await log_action(db, admin.id, "upload_town_resident_image", "town_resident", row.id,
                     old_value={"image_path": old_path}, new_value={"image_path": row.image_path}, ip_address=_ip(request))
    await db.commit()
    await db.refresh(row)
    return town_service.admin_resident_out(row)


@router.post("/residents/{row_id}/grant")
async def grant_resident(row_id: int, payload: GrantIn, request: Request,
                         db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    out = await town_service.admin_grant(db, row_id, payload.user_id)
    await log_action(db, admin.id, "grant_town_resident", "town_resident", row_id,
                     new_value={"user_id": payload.user_id}, ip_address=_ip(request))
    await db.commit()
    return out
