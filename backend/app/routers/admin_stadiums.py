from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.club_stadium_card import ClubStadiumCard
from app.models.stadium import Stadium
from app.models.user import User
from app.models.user_stadium_card import UserStadiumCard
from app.schemas.stadium import StadiumCreate, StadiumOut, StadiumUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_stadium_image, save_stadium_image
from app.services.stadium_service import create_stadium, get_stadium_or_404, update_stadium

router = APIRouter(prefix="/admin/stadiums", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[StadiumOut])
async def list_all_stadiums(
    search: Optional[str] = None,
    include_inactive: bool = True,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    query = select(Stadium)
    count_query = select(func.count(Stadium.id))
    if not include_inactive:
        query = query.where(Stadium.is_active.is_(True))
        count_query = count_query.where(Stadium.is_active.is_(True))
    if search:
        query = query.where(Stadium.display_name.ilike(f"%{search}%"))
        count_query = count_query.where(Stadium.display_name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Stadium.id.desc()).offset(params.offset).limit(params.page_size)
    stadiums = (await db.execute(query)).scalars().all()
    return Page.build([StadiumOut.model_validate(s) for s in stadiums], total, params)


@router.post("", response_model=StadiumOut)
async def create_stadium_route(
    payload: StadiumCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    stadium = await create_stadium(db, payload)
    await log_action(
        db, admin.id, "create_stadium", "stadium", stadium.id, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)


@router.put("/{stadium_id}", response_model=StadiumOut)
async def update_stadium_route(
    stadium_id: int, payload: StadiumUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    existing = await get_stadium_or_404(db, stadium_id)
    old_value = StadiumOut.model_validate(existing).model_dump(mode="json")
    stadium = await update_stadium(db, stadium_id, payload)
    await log_action(
        db, admin.id, "update_stadium", "stadium", stadium_id, old_value=old_value,
        new_value=payload.model_dump(exclude_unset=True, mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)


@router.post("/{stadium_id}/toggle-active", response_model=StadiumOut)
async def toggle_active(stadium_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stadium = await get_stadium_or_404(db, stadium_id)
    stadium.is_active = not stadium.is_active
    db.add(stadium)
    await log_action(
        db, admin.id, "toggle_stadium_active", "stadium", stadium_id, new_value={"is_active": stadium.is_active},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)


@router.post("/{stadium_id}/toggle-pack-droppable", response_model=StadiumOut)
async def toggle_pack_droppable(stadium_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stadium = await get_stadium_or_404(db, stadium_id)
    stadium.is_pack_droppable = not stadium.is_pack_droppable
    db.add(stadium)
    await log_action(
        db, admin.id, "toggle_stadium_pack_droppable", "stadium", stadium_id,
        new_value={"is_pack_droppable": stadium.is_pack_droppable}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)


@router.delete("/{stadium_id}")
async def delete_stadium(stadium_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stadium = await get_stadium_or_404(db, stadium_id)
    user_card_count = (
        await db.execute(select(func.count(UserStadiumCard.id)).where(UserStadiumCard.stadium_id == stadium_id))
    ).scalar_one()
    club_card_count = (
        await db.execute(select(func.count(ClubStadiumCard.id)).where(ClubStadiumCard.stadium_id == stadium_id))
    ).scalar_one()
    card_count = user_card_count + club_card_count
    if card_count > 0:
        raise ConflictError(
            f"Cannot delete: {card_count} card instance(s) reference this stadium. Deactivate it instead.",
            details={"user_card_count": user_card_count, "club_card_count": club_card_count},
        )
    await log_action(
        db, admin.id, "delete_stadium", "stadium", stadium_id, old_value={"display_name": stadium.display_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(stadium)
    await db.commit()
    delete_stadium_image(stadium.image_path)
    return {"status": "ok"}


@router.post("/{stadium_id}/image", response_model=StadiumOut)
async def upload_image(stadium_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stadium = await get_stadium_or_404(db, stadium_id)
    old_path = stadium.image_path
    new_path = await save_stadium_image(file, stadium.rarity, stadium.display_name)
    stadium.image_path = new_path
    db.add(stadium)
    if old_path:
        delete_stadium_image(old_path)
    await log_action(
        db, admin.id, "upload_stadium_image", "stadium", stadium_id, old_value={"image_path": old_path},
        new_value={"image_path": new_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)


@router.delete("/{stadium_id}/image", response_model=StadiumOut)
async def remove_image(stadium_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    stadium = await get_stadium_or_404(db, stadium_id)
    old_path = stadium.image_path
    delete_stadium_image(old_path)
    stadium.image_path = None
    db.add(stadium)
    await log_action(
        db, admin.id, "delete_stadium_image", "stadium", stadium_id, old_value={"image_path": old_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return StadiumOut.model_validate(stadium)
