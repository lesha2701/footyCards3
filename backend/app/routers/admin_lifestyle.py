from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.lifestyle import LifestyleItem
from app.models.user import User
from app.schemas.my_player import AdminLifestyleItemIn, AdminLifestyleItemOut, AdminLifestyleItemUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_lifestyle_image, save_lifestyle_image
from app.services.lifestyle_service import CATEGORIES, EFFECTS

router = APIRouter(prefix="/admin/lifestyle", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_or_404(db: AsyncSession, item_id: int) -> LifestyleItem:
    item = await db.get(LifestyleItem, item_id)
    if item is None:
        raise NotFoundError("Предмет не найден")
    return item


def _validate(item: LifestyleItem) -> None:
    if item.category not in CATEGORIES:
        raise ConflictError("Неизвестная категория")
    if item.coins_price <= 0 and item.stars_price <= 0:
        raise ConflictError("Укажи цену в монетах и/или в звёздах")
    if item.max_supply is not None and item.max_supply < item.sold_count:
        raise ConflictError("Нельзя сделать тираж меньше уже проданного")
    if (item.effect or "none") not in EFFECTS:
        raise ConflictError("Неизвестный эффект")
    if item.effect == "xp_bonus_pct" and item.effect_value > 100:
        raise ConflictError("Бонус опыта — не больше 100%")


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("", response_model=list[AdminLifestyleItemOut])
async def list_items(db: AsyncSession = Depends(get_db)):
    return (await db.execute(select(LifestyleItem).order_by(LifestyleItem.sort_order, LifestyleItem.id))).scalars().all()


@router.post("", response_model=AdminLifestyleItemOut)
async def create_item(
    payload: AdminLifestyleItemIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    item = LifestyleItem(**payload.model_dump(), sold_count=0)
    _validate(item)
    db.add(item)
    await db.flush()
    await log_action(db, admin.id, "create_lifestyle_item", "lifestyle_item", item.id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    await db.refresh(item)
    return item


@router.put("/{item_id}", response_model=AdminLifestyleItemOut)
async def update_item(
    item_id: int, payload: AdminLifestyleItemUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    item = await _get_or_404(db, item_id)
    old_value = AdminLifestyleItemOut.model_validate(item).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(item, key, value)
    _validate(item)
    await log_action(db, admin.id, "update_lifestyle_item", "lifestyle_item", item_id,
                     old_value=old_value, new_value=updates, ip_address=_ip(request))
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    """Only never-sold items can be deleted; a sold one is switched off
    (players keep what they bought)."""
    item = await _get_or_404(db, item_id)
    if item.sold_count > 0:
        raise ConflictError("Предмет уже покупали — выключи его вместо удаления")
    old_image = item.image_path
    await log_action(db, admin.id, "delete_lifestyle_item", "lifestyle_item", item_id,
                     old_value=AdminLifestyleItemOut.model_validate(item).model_dump(mode="json"), ip_address=_ip(request))
    await db.delete(item)
    await db.commit()
    delete_lifestyle_image(old_image)


@router.post("/{item_id}/image", response_model=AdminLifestyleItemOut)
async def upload_image(
    item_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    item = await _get_or_404(db, item_id)
    old_path = item.image_path
    item.image_path = await save_lifestyle_image(file, f"{item.id}_{item.name}")
    await log_action(db, admin.id, "upload_lifestyle_image", "lifestyle_item", item_id,
                     old_value={"image_path": old_path}, new_value={"image_path": item.image_path}, ip_address=_ip(request))
    await db.commit()
    await db.refresh(item)
    if old_path and old_path != item.image_path:
        delete_lifestyle_image(old_path)
    return item


@router.delete("/{item_id}/image", response_model=AdminLifestyleItemOut)
async def remove_image(
    item_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    item = await _get_or_404(db, item_id)
    old_path = item.image_path
    item.image_path = None
    await log_action(db, admin.id, "delete_lifestyle_image", "lifestyle_item", item_id,
                     old_value={"image_path": old_path}, ip_address=_ip(request))
    await db.commit()
    await db.refresh(item)
    delete_lifestyle_image(old_path)
    return item
