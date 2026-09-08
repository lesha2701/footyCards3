from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.club_coach_pack import ClubCoachPackOpenResult, ClubCoachPackOut, OpenClubCoachPackRequest
from app.services import club_coach_pack_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/coach-packs", response_model=list[ClubCoachPackOut])
async def list_club_coach_packs(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await club_coach_pack_service.list_club_coach_packs(db)


@router.post("/me/coach-packs/{club_coach_pack_id}/open", response_model=ClubCoachPackOpenResult)
async def open_club_coach_pack(
    club_coach_pack_id: int,
    payload: OpenClubCoachPackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_rate_limit(f"open_club_coach_pack:{user.id}", max_calls=10, window_seconds=60)
    return await club_coach_pack_service.open_club_coach_pack(db, user, club_coach_pack_id, payload.idempotency_key)
