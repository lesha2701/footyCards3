from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubJoinRequestOut, ClubSummaryOut, JoinByInviteIn, TransferCaptainIn
from app.schemas.club_pack import ClubPackOut
from app.schemas.club_pack_open import ClubPackOpenResult, OpenClubPackRequest
from app.schemas.club_squad import ClubCardOut, ClubLineupOut, ClubLineupSetRequest
from app.services import club_pack_service, club_service, club_squad_service

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("", response_model=list[ClubSummaryOut])
async def list_clubs(
    search: Optional[str] = Query(default=None), db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)
):
    return await club_service.list_clubs(db, search)


@router.get("/packs", response_model=list[ClubPackOut])
async def list_club_packs(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await club_pack_service.list_club_packs(db)


@router.get("/me", response_model=ClubDetailOut)
async def get_my_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_my_club_detail(db, user)


@router.get("/{club_id}", response_model=ClubDetailOut)
async def get_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.get_club_detail(db, club_id, requester_user_id=user.id)


@router.post("", response_model=ClubDetailOut)
async def create_club(
    payload: ClubCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await club_service.create_club(db, user, payload)


@router.post("/{club_id}/join", response_model=ClubDetailOut)
async def join_club(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_open_club(db, user, club_id)


@router.post("/{club_id}/join-requests", response_model=ClubJoinRequestOut)
async def create_join_request(club_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.create_join_request(db, user, club_id)


@router.get("/me/join-requests", response_model=list[ClubJoinRequestOut])
async def list_join_requests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.list_join_requests(db, user)


@router.post("/me/join-requests/{request_id}/accept", response_model=ClubDetailOut)
async def accept_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=True)
    return await club_service.get_my_club_detail(db, user)


@router.post("/me/join-requests/{request_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_join_request(request_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.respond_to_join_request(db, user, request_id, accept=False)


@router.post("/join-by-invite", response_model=ClubDetailOut)
async def join_by_invite(payload: JoinByInviteIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.join_by_invite(db, user, payload.invite_code)


@router.post("/me/leave", status_code=status.HTTP_200_OK)
async def leave_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.leave_club(db, user)
    return {"ok": True}


@router.post("/me/members/{user_id}/kick", response_model=ClubDetailOut)
async def kick_member(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.kick_member(db, user, user_id)


@router.post("/me/assistants/{user_id}/appoint", response_model=ClubDetailOut)
async def appoint_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.appoint_assistant(db, user, user_id)


@router.post("/me/assistants/{user_id}/remove", response_model=ClubDetailOut)
async def remove_assistant(user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.remove_assistant(db, user, user_id)


@router.post("/me/transfer-captain", response_model=ClubDetailOut)
async def transfer_captain(payload: TransferCaptainIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.transfer_captain(db, user, payload.user_id)


@router.post("/me/disband", status_code=status.HTTP_204_NO_CONTENT)
async def disband_club(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_service.disband_club(db, user)


@router.post("/me/daily-claim", response_model=ClubDetailOut)
async def claim_daily_reward(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.claim_daily_reward(db, user)


@router.get("/me/lineup", response_model=ClubLineupOut)
async def get_club_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.get_club_lineup(db, user)


@router.put("/me/lineup", response_model=ClubLineupOut)
async def set_club_lineup(payload: ClubLineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.set_club_lineup(db, user, payload)


@router.get("/me/cards", response_model=list[ClubCardOut])
async def list_club_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_squad_service.list_club_cards(db, user)


@router.post("/me/packs/{club_pack_id}/open", response_model=ClubPackOpenResult)
async def open_club_pack(club_pack_id: int, payload: OpenClubPackRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    check_rate_limit(f"open_club_pack:{user.id}", max_calls=10, window_seconds=60)
    return await club_pack_service.open_club_pack(db, user, club_pack_id, payload.idempotency_key)
