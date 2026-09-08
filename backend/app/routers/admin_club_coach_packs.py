from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.club_coach_pack import ClubCoachPack, ClubCoachPackRarityProbability
from app.models.user import User
from app.routers.admin_club_packs import _validate_probabilities
from app.schemas.club_coach_pack import ClubCoachPackCreate, ClubCoachPackOut, ClubCoachPackUpdate
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/club-coach-packs", tags=["admin"], dependencies=[Depends(get_current_admin)])


async def _get_pack_or_404(db: AsyncSession, pack_id: int) -> ClubCoachPack:
    result = await db.execute(
        select(ClubCoachPack).where(ClubCoachPack.id == pack_id).options(joinedload(ClubCoachPack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if pack is None:
        raise NotFoundError("Club coach pack not found")
    return pack


@router.get("", response_model=list[ClubCoachPackOut])
async def list_all_club_coach_packs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ClubCoachPack).options(joinedload(ClubCoachPack.rarity_probabilities)).order_by(ClubCoachPack.sort_order))
    return result.unique().scalars().all()


@router.post("", response_model=ClubCoachPackOut)
async def create_club_coach_pack(payload: ClubCoachPackCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    _validate_probabilities(payload.rarity_probabilities)
    data = payload.model_dump(exclude={"rarity_probabilities"})
    pack = ClubCoachPack(**data)
    db.add(pack)
    await db.flush()
    for p in payload.rarity_probabilities:
        db.add(ClubCoachPackRarityProbability(club_coach_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    await log_action(db, admin.id, "create_club_coach_pack", "club_coach_pack", pack.id, new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack.id)


@router.put("/{pack_id}", response_model=ClubCoachPackOut)
async def update_club_coach_pack(pack_id: int, payload: ClubCoachPackUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    pack = await _get_pack_or_404(db, pack_id)
    old_value = ClubCoachPackOut.model_validate(pack).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True, exclude={"rarity_probabilities"})
    for key, value in updates.items():
        setattr(pack, key, value)
    if payload.rarity_probabilities is not None:
        _validate_probabilities(payload.rarity_probabilities)
        for existing in list(pack.rarity_probabilities):
            await db.delete(existing)
        await db.flush()
        for p in payload.rarity_probabilities:
            db.add(ClubCoachPackRarityProbability(club_coach_pack_id=pack.id, rarity=p.rarity, probability=p.probability))
    # No db.add(pack) here: pack is already persistent (loaded via SELECT above), and
    # re-adding it cascades save-update over rarity_probabilities (cascade="all,
    # delete-orphan") — which, right after the delete loop above, still holds Python-side
    # references to the now-deleted rows, crashing with "Instance has been deleted."
    await log_action(db, admin.id, "update_club_coach_pack", "club_coach_pack", pack_id, old_value=old_value, new_value=payload.model_dump(mode="json", exclude_unset=True), ip_address=request.client.host if request.client else None)
    await db.commit()
    return await _get_pack_or_404(db, pack_id)
