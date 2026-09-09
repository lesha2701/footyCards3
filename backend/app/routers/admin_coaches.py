from typing import Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.club_coach_card import ClubCoachCard
from app.models.coach import Coach
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
from app.schemas.coach import CoachCreate, CoachOut, CoachUpdate
from app.services.admin_log_service import log_action
from app.services.coach_service import create_coach, get_coach_or_404, update_coach
from app.services.image_service import delete_coach_image, save_coach_image

router = APIRouter(prefix="/admin/coaches", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=Page[CoachOut])
async def list_all_coaches(
    search: Optional[str] = None,
    include_inactive: bool = True,
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    # CoachOut nests boosts, so the list route needs an eager load (unlike
    # PlayerOut in admin_players.py, which has no nested relationship) —
    # without it, CoachOut.model_validate's attribute access on `.boosts`
    # would lazy-load, which fails under async SQLAlchemy (MissingGreenlet).
    query = select(Coach).options(selectinload(Coach.boosts))
    count_query = select(func.count(Coach.id))
    if not include_inactive:
        query = query.where(Coach.is_active.is_(True))
        count_query = count_query.where(Coach.is_active.is_(True))
    if search:
        query = query.where(Coach.display_name.ilike(f"%{search}%"))
        count_query = count_query.where(Coach.display_name.ilike(f"%{search}%"))

    total = (await db.execute(count_query)).scalar_one()
    query = query.order_by(Coach.id.desc()).offset(params.offset).limit(params.page_size)
    coaches = (await db.execute(query)).unique().scalars().all()
    return Page.build([CoachOut.model_validate(c) for c in coaches], total, params)


@router.post("", response_model=CoachOut)
async def create_coach_route(
    payload: CoachCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    coach = await create_coach(db, payload)
    await log_action(
        db, admin.id, "create_coach", "coach", coach.id, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.put("/{coach_id}", response_model=CoachOut)
async def update_coach_route(
    coach_id: int, payload: CoachUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)
):
    existing = await get_coach_or_404(db, coach_id)
    # get_coach_or_404 uses db.get(), which doesn't eager-load boosts —
    # refresh explicitly so the CoachOut snapshot below doesn't trigger a
    # lazy load (unsupported under async SQLAlchemy, MissingGreenlet).
    await db.refresh(existing, attribute_names=["boosts"])
    old_value = CoachOut.model_validate(existing).model_dump(mode="json")
    coach = await update_coach(db, coach_id, payload)
    await log_action(
        db, admin.id, "update_coach", "coach", coach_id, old_value=old_value,
        new_value=payload.model_dump(exclude_unset=True, mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.post("/{coach_id}/toggle-active", response_model=CoachOut)
async def toggle_active(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await get_coach_or_404(db, coach_id)
    coach.is_active = not coach.is_active
    db.add(coach)
    await log_action(
        db, admin.id, "toggle_coach_active", "coach", coach_id, new_value={"is_active": coach.is_active},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.post("/{coach_id}/toggle-pack-droppable", response_model=CoachOut)
async def toggle_pack_droppable(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await get_coach_or_404(db, coach_id)
    coach.is_pack_droppable = not coach.is_pack_droppable
    db.add(coach)
    await log_action(
        db, admin.id, "toggle_coach_pack_droppable", "coach", coach_id,
        new_value={"is_pack_droppable": coach.is_pack_droppable}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.delete("/{coach_id}")
async def delete_coach(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await get_coach_or_404(db, coach_id)
    user_card_count = (
        await db.execute(select(func.count(UserCoachCard.id)).where(UserCoachCard.coach_id == coach_id))
    ).scalar_one()
    club_card_count = (
        await db.execute(select(func.count(ClubCoachCard.id)).where(ClubCoachCard.coach_id == coach_id))
    ).scalar_one()
    card_count = user_card_count + club_card_count
    if card_count > 0:
        raise ConflictError(
            f"Cannot delete: {card_count} card instance(s) reference this coach. Deactivate it instead.",
            details={"user_card_count": user_card_count, "club_card_count": club_card_count},
        )
    await log_action(
        db, admin.id, "delete_coach", "coach", coach_id, old_value={"display_name": coach.display_name},
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(coach)
    await db.commit()
    delete_coach_image(coach.image_path)
    return {"status": "ok"}


@router.post("/{coach_id}/image", response_model=CoachOut)
async def upload_image(coach_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await get_coach_or_404(db, coach_id)
    old_path = coach.image_path
    new_path = await save_coach_image(file, coach.rarity, coach.display_name)
    coach.image_path = new_path
    db.add(coach)
    if old_path:
        delete_coach_image(old_path)
    await log_action(
        db, admin.id, "upload_coach_image", "coach", coach_id, old_value={"image_path": old_path},
        new_value={"image_path": new_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)


@router.delete("/{coach_id}/image", response_model=CoachOut)
async def remove_image(coach_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    coach = await get_coach_or_404(db, coach_id)
    old_path = coach.image_path
    delete_coach_image(old_path)
    coach.image_path = None
    db.add(coach)
    await log_action(
        db, admin.id, "delete_coach_image", "coach", coach_id, old_value={"image_path": old_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(coach, attribute_names=["boosts"])
    return CoachOut.model_validate(coach)
