from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.user import User
from app.services import club_base_service
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config
from app.services.image_service import delete_club_base_image, save_club_base_image

# Settings themselves (buildings, caps, Stars per hour, income days) are
# GameConfig fields edited through PUT /admin/games/config.
router = APIRouter(prefix="/admin/club-base", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request):
    return request.client.host if request.client else None


def _check_slot(slot: str) -> None:
    if slot != "background" and slot not in club_base_service.BUILDINGS:
        raise NotFoundError("Нет такого места для картинки")


def _get(art: dict, slot: str) -> Optional[str]:
    return art.get("background") if slot == "background" else (art.get("buildings") or {}).get(slot)


def _set(art: dict, slot: str, path: Optional[str]) -> dict:
    art = {"background": art.get("background"), "buildings": dict(art.get("buildings") or {})}
    if slot == "background":
        art["background"] = path
    elif path:
        art["buildings"][slot] = path
    else:
        art["buildings"].pop(slot, None)
    return art


@router.get("/art")
async def get_art(db: AsyncSession = Depends(get_db)):
    config = await get_config(db)
    return {"art": club_base_service.art_out(config),
            "slots": [{"code": "background", "name": "Фон карты"}]
            + [{"code": b.code, "name": b.name} for b in club_base_service.BUILDINGS.values()]}


@router.post("/art/{slot}")
async def upload_art(slot: str, request: Request, file: UploadFile = File(...),
                     db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    _check_slot(slot)
    config = await get_config(db)
    art = config.club_base_art or {}
    old_path = _get(art, slot)
    path = await save_club_base_image(file, f"base_{slot}")
    config.club_base_art = _set(art, slot, path)
    db.add(config)
    await log_action(db, admin.id, "upload_club_base_art", "game_config", config.id,
                     old_value={"slot": slot, "path": old_path}, new_value={"slot": slot, "path": path},
                     ip_address=_ip(request))
    await db.commit()
    if old_path and old_path != path:
        delete_club_base_image(old_path)
    return {"art": club_base_service.art_out(config)}


@router.delete("/art/{slot}")
async def delete_art(slot: str, request: Request, db: AsyncSession = Depends(get_db),
                     admin: User = Depends(get_current_admin)):
    _check_slot(slot)
    config = await get_config(db)
    art = config.club_base_art or {}
    old_path = _get(art, slot)
    config.club_base_art = _set(art, slot, None)
    db.add(config)
    await log_action(db, admin.id, "delete_club_base_art", "game_config", config.id,
                     old_value={"slot": slot, "path": old_path}, ip_address=_ip(request))
    await db.commit()
    delete_club_base_image(old_path)
    return {"art": club_base_service.art_out(config)}


@router.get("/ledger")
async def ledger(user_id: Optional[int] = None, limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Journal of every base operation (upgrades, speed-ups, completions, income)."""
    return await club_base_service.admin_ledger(db, user_id, limit)
