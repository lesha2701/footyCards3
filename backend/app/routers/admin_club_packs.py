from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.user import User
from app.schemas.club_pack import ClubPackCreate, ClubPackOut, ClubPackUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_pack_image, save_pack_image

router = APIRouter(prefix="/admin/club-packs", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_pack_or_404(db: AsyncSession, pack_id: int) -> ClubPack:
    result = await db.execute(
        select(ClubPack).where(ClubPack.id == pack_id).options(joinedload(ClubPack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if pack is None:
        raise NotFoundError("Club pack not found")
    return pack


def _validate_probabilities(rarity_probabilities: list) -> None:
    total = sum(p.probability for p in rarity_probabilities)
    if not (0.98 <= total <= 1.02):
        raise ConflictError(f"Вероятности должны суммироваться к 1.0 (сейчас {total:.4f})")


@router.get("", response_model=list[ClubPackOut])
async def list_all_club_packs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClubPack).options(joinedload(ClubPack.rarity_probabilities)).order_by(ClubPack.sort_order))
    return result.unique().scalars().all()


@router.post("", response_model=ClubPackOut)
async def create_club_pack(payload: ClubPackCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    _validate_probabilities(payload.rarity_probabilities)
    data = payload.model_dump(exclude={"rarity_probabilities"})
    pack = ClubPack(**data)
    db.add(pack)
    await db.flush()
    for p in payload.rarity_probabilities:
        db.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    await log_action(db, admin.id, "create_club_pack", "club_pack", pack.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack.id)


@router.put("/{pack_id}", response_model=ClubPackOut)
async def update_club_pack(pack_id: int, payload: ClubPackUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_value = ClubPackOut.model_validate(pack).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"rarity_probabilities"})
    for key, value in updates.items():
        setattr(pack, key, value)
    if payload.rarity_probabilities is not None:
        _validate_probabilities(payload.rarity_probabilities)
        for existing in list(pack.rarity_probabilities):
            await db.delete(existing)
        await db.flush()
        for p in payload.rarity_probabilities:
            db.add(ClubPackRarityProbability(club_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    db.add(pack)
    await log_action(db, admin.id, "update_club_pack", "club_pack", pack_id, old_value=old_value, new_value=payload.model_dump(mode="json", exclude_unset=True), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack_id)


@router.post("/{pack_id}/image", response_model=ClubPackOut)
async def upload_club_pack_image(pack_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_image = pack.image_path
    pack.image_path = await save_pack_image(file, f"club-{pack.slug}")
    db.add(pack)
    await db.commit()
    delete_pack_image(old_image)
    return await _get_pack_or_404(db, pack_id)


@router.post("/{pack_id}/toggle-active", response_model=ClubPackOut)
async def toggle_club_pack_active(pack_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    pack.is_active = not pack.is_active
    db.add(pack)
    await log_action(db, admin.id, "toggle_club_pack_active", "club_pack", pack_id, new_value={"is_active": pack.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack_id)


@router.delete("/{pack_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_club_pack(pack_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    await log_action(db, admin.id, "delete_club_pack", "club_pack", pack_id, old_value=ClubPackOut.model_validate(pack).model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    delete_pack_image(pack.image_path)
    await db.delete(pack)
    await db.commit()
