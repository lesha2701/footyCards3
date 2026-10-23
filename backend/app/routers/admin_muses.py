from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.muse import Muse, MuseAccessory, MuseCollection
from app.models.user import User
from app.schemas.muse import MuseAccessoryIn, MuseCollectionIn, MuseGrantIn, MuseIn
from app.services import muse_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_muse_image, save_muse_image

router = APIRouter(prefix="/admin/muses", tags=["admin"], dependencies=[Depends(get_current_admin)])

# kind -> (model, saver, out, not-found message)
KINDS = {
    "collections": (MuseCollection, muse_service.admin_save_collection, muse_service.admin_collection_out, "Коллекция не найдена"),
    "muses": (Muse, muse_service.admin_save_muse, muse_service.admin_muse_out, "Муза не найдена"),
    "accessories": (MuseAccessory, muse_service.admin_save_accessory, muse_service.admin_accessory_out, "Подарок не найден"),
}


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("")
async def catalog(db: AsyncSession = Depends(get_db)):
    return await muse_service.admin_catalog(db)


async def _save(db: AsyncSession, admin: User, request: Request, kind: str, payload, row_id=None) -> dict:
    _model, saver, _out, _missing = KINDS[kind]
    out = await saver(db, payload.model_dump(), row_id)
    await log_action(db, admin.id, f"{'update' if row_id else 'create'}_muse_{kind}", f"muse_{kind}", out["id"],
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.post("/collections")
async def create_collection(payload: MuseCollectionIn, request: Request, db: AsyncSession = Depends(get_db),
                            admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "collections", payload)


@router.put("/collections/{row_id}")
async def update_collection(row_id: int, payload: MuseCollectionIn, request: Request, db: AsyncSession = Depends(get_db),
                            admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "collections", payload, row_id)


@router.post("/muses")
async def create_muse(payload: MuseIn, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "muses", payload)


@router.put("/muses/{row_id}")
async def update_muse(row_id: int, payload: MuseIn, request: Request, db: AsyncSession = Depends(get_db),
                      admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "muses", payload, row_id)


@router.post("/accessories")
async def create_accessory(payload: MuseAccessoryIn, request: Request, db: AsyncSession = Depends(get_db),
                           admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "accessories", payload)


@router.put("/accessories/{row_id}")
async def update_accessory(row_id: int, payload: MuseAccessoryIn, request: Request, db: AsyncSession = Depends(get_db),
                           admin: User = Depends(get_current_admin)):
    return await _save(db, admin, request, "accessories", payload, row_id)


@router.post("/{kind}/{row_id}/image")
async def upload_image(
    kind: str, row_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    if kind not in KINDS:
        raise NotFoundError("Not found")
    model, _saver, out, missing = KINDS[kind]
    row = await db.get(model, row_id)
    if row is None:
        raise NotFoundError(missing)
    old_path = row.image_path
    row.image_path = await save_muse_image(file, row.name)
    delete_muse_image(old_path)
    await log_action(db, admin.id, f"upload_muse_{kind}_image", f"muse_{kind}", row.id,
                     old_value={"image_path": old_path}, new_value={"image_path": row.image_path}, ip_address=_ip(request))
    await db.commit()
    await db.refresh(row)
    return out(row)


@router.post("/muses/{muse_id}/grant")
async def grant_muse(
    muse_id: int, payload: MuseGrantIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await muse_service.admin_grant(db, muse_id, payload.user_id)
    await log_action(db, admin.id, "grant_muse", "muse", muse_id, new_value={"user_id": payload.user_id},
                     ip_address=_ip(request))
    await db.commit()
    return out
