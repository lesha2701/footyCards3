from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.gift import GiftSet
from app.models.user import User
from app.schemas.gift import (
    AdminGiftBroadcastIn,
    AdminGiftBroadcastOut,
    AdminGiftSendIn,
    GiftOut,
    GiftSetCreate,
    GiftSetOut,
    GiftSetUpdate,
)
from app.services import gift_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_gift_set_image, save_gift_set_image

router = APIRouter(prefix="/admin/gifts", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_gift_set_or_404(db: AsyncSession, gift_set_id: int) -> GiftSet:
    gift_set = await db.get(GiftSet, gift_set_id)
    if gift_set is None:
        raise NotFoundError("Gift set not found")
    return gift_set


@router.get("/sets", response_model=list[GiftSetOut])
async def list_all_gift_sets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GiftSet).order_by(GiftSet.sort_order))
    return result.scalars().all()


@router.post("/sets", response_model=GiftSetOut)
async def create_gift_set(
    payload: GiftSetCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    gift_set = GiftSet(**payload.model_dump())
    db.add(gift_set)
    await db.flush()
    await log_action(
        db, admin.id, "create_gift_set", "gift_set", gift_set.id,
        new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(gift_set)
    return gift_set


@router.put("/sets/{gift_set_id}", response_model=GiftSetOut)
async def update_gift_set(
    gift_set_id: int, payload: GiftSetUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    gift_set = await _get_gift_set_or_404(db, gift_set_id)
    old_value = GiftSetOut.model_validate(gift_set).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(gift_set, key, value)
    db.add(gift_set)

    await log_action(
        db, admin.id, "update_gift_set", "gift_set", gift_set_id,
        old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(gift_set)
    return gift_set


@router.delete("/sets/{gift_set_id}/image", response_model=GiftSetOut)
async def remove_gift_set_image(
    gift_set_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    gift_set = await _get_gift_set_or_404(db, gift_set_id)
    old_path = gift_set.image_path
    delete_gift_set_image(old_path)
    gift_set.image_path = None
    db.add(gift_set)
    await log_action(
        db, admin.id, "delete_gift_set_image", "gift_set", gift_set_id,
        old_value={"image_path": old_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(gift_set)
    return gift_set


@router.delete("/sets/{gift_set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gift_set(
    gift_set_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    gift_set = await _get_gift_set_or_404(db, gift_set_id)
    old_image_path = gift_set.image_path
    await log_action(
        db, admin.id, "delete_gift_set", "gift_set", gift_set_id,
        old_value=GiftSetOut.model_validate(gift_set).model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(gift_set)
    await db.commit()
    delete_gift_set_image(old_image_path)


@router.post("/sets/{gift_set_id}/image", response_model=GiftSetOut)
async def upload_gift_set_image(
    gift_set_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    gift_set = await _get_gift_set_or_404(db, gift_set_id)
    old_path = gift_set.image_path
    new_path = await save_gift_set_image(file, gift_set.name)
    gift_set.image_path = new_path
    db.add(gift_set)
    delete_gift_set_image(old_path)
    await log_action(
        db, admin.id, "upload_gift_set_image", "gift_set", gift_set_id,
        old_value={"image_path": old_path}, new_value={"image_path": new_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(gift_set)
    return gift_set


@router.post("/send", response_model=GiftOut)
async def send_gift_to_user(
    payload: AdminGiftSendIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    gift = await gift_service.admin_send_gift_to_user(db, payload.gift_set_id, payload.user_id, payload.message)
    await log_action(
        db, admin.id, "send_gift", "gift", gift.id,
        new_value={"gift_set_id": payload.gift_set_id, "user_id": payload.user_id, "message": payload.message},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return gift


@router.post("/broadcast", response_model=AdminGiftBroadcastOut)
async def broadcast_gift(
    payload: AdminGiftBroadcastIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    recipients = await gift_service.admin_broadcast_gift(db, payload.gift_set_id, payload.message)
    await log_action(
        db, admin.id, "broadcast_gift", "gift_set", payload.gift_set_id,
        new_value={"message": payload.message, "recipients": recipients},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return AdminGiftBroadcastOut(recipients=recipients)
