from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.equipment import EquipmentCollection, EquipmentItem
from app.models.user import User
from app.schemas.equipment import EquipmentCollectionIn, EquipmentGrantIn, EquipmentItemIn
from app.services import equipment_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_equipment_image, save_equipment_image

router = APIRouter(prefix="/admin/equipment", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("")
async def catalog(db: AsyncSession = Depends(get_db)):
    return await equipment_service.admin_catalog(db)


@router.post("/items")
async def create_item(
    payload: EquipmentItemIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await equipment_service.admin_save_item(db, payload.model_dump())
    await log_action(db, admin.id, "create_equipment_item", "equipment_item", out["id"],
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/items/{item_id}")
async def update_item(
    item_id: int, payload: EquipmentItemIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await equipment_service.admin_save_item(db, payload.model_dump(), item_id)
    await log_action(db, admin.id, "update_equipment_item", "equipment_item", item_id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.post("/collections")
async def create_collection(
    payload: EquipmentCollectionIn, request: Request, db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    out = await equipment_service.admin_save_collection(db, payload.model_dump())
    await log_action(db, admin.id, "create_equipment_collection", "equipment_collection", out["id"],
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/collections/{collection_id}")
async def update_collection(
    collection_id: int, payload: EquipmentCollectionIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await equipment_service.admin_save_collection(db, payload.model_dump(), collection_id)
    await log_action(db, admin.id, "update_equipment_collection", "equipment_collection", collection_id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


async def _upload(db: AsyncSession, row, file: UploadFile, kind: str, admin: User, request: Request) -> None:
    old_path = row.image_path
    row.image_path = await save_equipment_image(file, row.name)
    delete_equipment_image(old_path)
    await log_action(db, admin.id, f"upload_equipment_{kind}_image", f"equipment_{kind}", row.id,
                     old_value={"image_path": old_path}, new_value={"image_path": row.image_path}, ip_address=_ip(request))
    await db.commit()
    await db.refresh(row)


@router.post("/items/{item_id}/image")
async def upload_item_image(
    item_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    item = await db.get(EquipmentItem, item_id)
    if item is None:
        raise NotFoundError("Вещь не найдена")
    await _upload(db, item, file, "item", admin, request)
    return equipment_service.admin_item_out(item)


@router.post("/collections/{collection_id}/image")
async def upload_collection_image(
    collection_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    collection = await db.get(EquipmentCollection, collection_id)
    if collection is None:
        raise NotFoundError("Коллекция не найдена")
    await _upload(db, collection, file, "collection", admin, request)
    return equipment_service.admin_collection_out(collection)


@router.post("/items/{item_id}/grant")
async def grant_item(
    item_id: int, payload: EquipmentGrantIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await equipment_service.admin_grant(db, item_id, payload.user_id)
    await log_action(db, admin.id, "grant_equipment_item", "equipment_item", item_id,
                     new_value={"user_id": payload.user_id}, ip_address=_ip(request))
    await db.commit()
    return out
