from collections import Counter

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.pack import Pack, PackRarityProbability
from app.models.user import User
from app.schemas.admin import PackPreviewOut, PackRarityStatOut
from app.schemas.pack import PackCreate, PackOut, PackUpdate
from app.services.admin_log_service import log_action
from app.services.image_service import delete_pack_image, save_pack_image
from app.services.pack_service import roll_rarities

router = APIRouter(prefix="/admin/packs", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _validate_probabilities(rarity_probabilities: list) -> None:
    total = sum(p.probability for p in rarity_probabilities)
    if not (0.98 <= total <= 1.02):
        raise ConflictError(f"Rarity probabilities must sum to 1.0 (got {total:.4f})")


@router.get("", response_model=list[PackOut])
async def list_all_packs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Pack).options(joinedload(Pack.rarity_probabilities)).order_by(Pack.sort_order))
    packs = result.unique().scalars().all()
    return [PackOut.model_validate(p) for p in packs]


@router.post("", response_model=PackOut)
async def create_pack(payload: PackCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    _validate_probabilities(payload.rarity_probabilities)
    data = payload.model_dump(exclude={"rarity_probabilities"})
    pack = Pack(**data)
    db.add(pack)
    await db.flush()
    for rp in payload.rarity_probabilities:
        db.add(PackRarityProbability(pack_id=pack.id, rarity=rp.rarity, probability=rp.probability))
    await log_action(db, admin.id, "create_pack", "pack", pack.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_out(db, pack.id)


async def _get_pack_out(db: AsyncSession, pack_id: int) -> PackOut:
    result = await db.execute(select(Pack).where(Pack.id == pack_id).options(joinedload(Pack.rarity_probabilities)))
    pack = result.unique().scalar_one()
    return PackOut.model_validate(pack)


async def _get_pack_or_404(db: AsyncSession, pack_id: int) -> Pack:
    result = await db.execute(select(Pack).where(Pack.id == pack_id).options(joinedload(Pack.rarity_probabilities)))
    pack = result.unique().scalar_one_or_none()
    if not pack:
        raise NotFoundError("Pack not found")
    return pack


@router.put("/{pack_id}", response_model=PackOut)
async def update_pack(pack_id: int, payload: PackUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_value = PackOut.model_validate(pack).model_dump(mode="json")
    old_image_path = pack.image_path

    updates = payload.model_dump(exclude_unset=True, exclude={"rarity_probabilities"})
    for key, value in updates.items():
        setattr(pack, key, value)

    if "image_path" in updates and old_image_path and old_image_path != pack.image_path:
        delete_pack_image(old_image_path)

    if payload.rarity_probabilities is not None:
        _validate_probabilities(payload.rarity_probabilities)
        for rp in list(pack.rarity_probabilities):
            await db.delete(rp)
        await db.flush()
        for rp in payload.rarity_probabilities:
            db.add(PackRarityProbability(pack_id=pack.id, rarity=rp.rarity, probability=rp.probability))

    db.add(pack)
    await log_action(
        db, admin.id, "update_pack", "pack", pack_id, old_value=old_value,
        new_value=payload.model_dump(mode="json", exclude_unset=True),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return await _get_pack_out(db, pack_id)


@router.post("/{pack_id}/image", response_model=PackOut)
async def upload_pack_image(pack_id: int, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_path = pack.image_path
    new_path = await save_pack_image(file, pack.slug)
    pack.image_path = new_path
    db.add(pack)
    delete_pack_image(old_path)
    await log_action(db, admin.id, "upload_pack_image", "pack", pack_id, old_value={"image_path": old_path}, new_value={"image_path": new_path}, ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_out(db, pack_id)


@router.post("/{pack_id}/toggle-active", response_model=PackOut)
async def toggle_pack_active(pack_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    pack.is_active = not pack.is_active
    db.add(pack)
    await log_action(db, admin.id, "toggle_pack_active", "pack", pack_id, new_value={"is_active": pack.is_active}, ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_out(db, pack_id)


@router.get("/{pack_id}/preview", response_model=PackPreviewOut)
async def preview_pack(pack_id: int, simulations: int = Query(default=1000, ge=10, le=20000), db: AsyncSession = Depends(get_db)):
    pack = await _get_pack_or_404(db, pack_id)
    counter: Counter = Counter()
    for _ in range(simulations):
        rolled = roll_rarities(pack.rarity_probabilities, pack.card_count, pack.guaranteed_min_rarity)
        counter.update(rolled)

    total_cards = simulations * pack.card_count
    stats = [
        PackRarityStatOut(rarity=rarity, count=count, percentage=round(count / total_cards * 100, 2))
        for rarity, count in counter.items()
    ]
    return PackPreviewOut(simulations=simulations, cards_per_open=pack.card_count, rarity_distribution=stats)
