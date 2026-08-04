from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.badge import Badge
from app.models.user import User
from app.schemas.badge import BadgeCreate, BadgeOut, BadgeUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_badge_image, save_badge_image

router = APIRouter(prefix="/admin/badges", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_badge_or_404(db: AsyncSession, badge_id: int) -> Badge:
    badge = await db.get(Badge, badge_id)
    if badge is None:
        raise NotFoundError("Badge not found")
    return badge


@router.get("", response_model=list[BadgeOut])
async def list_all_badges(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Badge).order_by(Badge.sort_order))
    return result.scalars().all()


@router.post("", response_model=BadgeOut)
async def create_badge(payload: BadgeCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    badge = Badge(**payload.model_dump())
    db.add(badge)
    await db.flush()
    await log_action(
        db, admin.id, "create_badge", "badge", badge.id,
        new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(badge)
    return badge


@router.put("/{badge_id}", response_model=BadgeOut)
async def update_badge(badge_id: int, payload: BadgeUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    badge = await _get_badge_or_404(db, badge_id)
    old_value = BadgeOut.model_validate(badge).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(badge, key, value)
    db.add(badge)

    await log_action(
        db, admin.id, "update_badge", "badge", badge_id,
        old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(badge)
    return badge


@router.delete("/{badge_id}/image", response_model=BadgeOut)
async def remove_badge_image(badge_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    badge = await _get_badge_or_404(db, badge_id)
    old_path = badge.image_path
    delete_badge_image(old_path)
    badge.image_path = None
    db.add(badge)
    await log_action(
        db, admin.id, "delete_badge_image", "badge", badge_id,
        old_value={"image_path": old_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(badge)
    return badge


@router.delete("/{badge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_badge(badge_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    badge = await _get_badge_or_404(db, badge_id)
    old_image_path = badge.image_path
    await log_action(
        db, admin.id, "delete_badge", "badge", badge_id,
        old_value=BadgeOut.model_validate(badge).model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(badge)
    await db.commit()
    delete_badge_image(old_image_path)


@router.post("/{badge_id}/image", response_model=BadgeOut)
async def upload_badge_image(badge_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    badge = await _get_badge_or_404(db, badge_id)
    old_path = badge.image_path
    new_path = await save_badge_image(file, badge.name)
    badge.image_path = new_path
    db.add(badge)
    delete_badge_image(old_path)
    await log_action(
        db, admin.id, "upload_badge_image", "badge", badge_id,
        old_value={"image_path": old_path}, new_value={"image_path": new_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(badge)
    return badge
