from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.trophy import TrophyDefinition
from app.models.user import User
from app.schemas.trophy import TrophyDefinitionCreate, TrophyDefinitionOut, TrophyDefinitionUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_trophy_image, save_trophy_image

router = APIRouter(prefix="/admin/trophies", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_trophy_or_404(db: AsyncSession, trophy_id: int) -> TrophyDefinition:
    trophy = await db.get(TrophyDefinition, trophy_id)
    if trophy is None:
        raise NotFoundError("Trophy not found")
    return trophy


@router.get("", response_model=list[TrophyDefinitionOut])
async def list_all_trophies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TrophyDefinition).order_by(TrophyDefinition.sort_order))
    return result.scalars().all()


@router.post("", response_model=TrophyDefinitionOut)
async def create_trophy(payload: TrophyDefinitionCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    trophy = TrophyDefinition(**payload.model_dump())
    db.add(trophy)
    await db.flush()
    await log_action(
        db, admin.id, "create_trophy", "trophy_definition", trophy.id,
        new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(trophy)
    return trophy


@router.put("/{trophy_id}", response_model=TrophyDefinitionOut)
async def update_trophy(trophy_id: int, payload: TrophyDefinitionUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    trophy = await _get_trophy_or_404(db, trophy_id)
    old_value = TrophyDefinitionOut.model_validate(trophy).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(trophy, key, value)
    db.add(trophy)

    await log_action(
        db, admin.id, "update_trophy", "trophy_definition", trophy_id,
        old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(trophy)
    return trophy


@router.delete("/{trophy_id}/image", response_model=TrophyDefinitionOut)
async def remove_trophy_image(trophy_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    trophy = await _get_trophy_or_404(db, trophy_id)
    old_path = trophy.image_path
    delete_trophy_image(old_path)
    trophy.image_path = None
    db.add(trophy)
    await log_action(
        db, admin.id, "delete_trophy_image", "trophy_definition", trophy_id,
        old_value={"image_path": old_path}, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(trophy)
    return trophy


@router.delete("/{trophy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trophy(trophy_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    trophy = await _get_trophy_or_404(db, trophy_id)
    old_image_path = trophy.image_path
    await log_action(
        db, admin.id, "delete_trophy", "trophy_definition", trophy_id,
        old_value=TrophyDefinitionOut.model_validate(trophy).model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(trophy)
    await db.commit()
    delete_trophy_image(old_image_path)


@router.post("/{trophy_id}/image", response_model=TrophyDefinitionOut)
async def upload_trophy_image(trophy_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    trophy = await _get_trophy_or_404(db, trophy_id)
    old_path = trophy.image_path
    new_path = await save_trophy_image(file, trophy.name)
    trophy.image_path = new_path
    db.add(trophy)
    delete_trophy_image(old_path)
    await log_action(
        db, admin.id, "upload_trophy_image", "trophy_definition", trophy_id,
        old_value={"image_path": old_path}, new_value={"image_path": new_path},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(trophy)
    return trophy
