from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.mordoboi import (
    MordoboiBotMatchRequest,
    MordoboiBrutalityRequest,
    MordoboiBoxerOut,
    MordoboiBoxerSetRequest,
    MordoboiChallengeRequest,
    MordoboiClubRingOut,
    MordoboiLegendOut,
    MordoboiNicknameRequest,
    MordoboiInfoOut,
    MordoboiMatchOut,
    MordoboiOpenChallengePreviewOut,
    MordoboiOpenChallengeRequest,
    MordoboiPickRequest,
    MordoboiSearchStatusOut,
    MordoboiStatsOut,
)
from app.services import mordoboi_service

router = APIRouter(prefix="/mordoboi", tags=["mordoboi"])


@router.get("/info", response_model=MordoboiInfoOut)
async def get_info(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_info(db, user)


@router.get("/stats", response_model=MordoboiStatsOut)
async def get_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_stats(db, user)


@router.get("/boxer", response_model=MordoboiBoxerOut)
async def get_boxer(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_boxer(db, user)


@router.put("/boxer", response_model=MordoboiBoxerOut)
async def set_boxer(
    payload: MordoboiBoxerSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await mordoboi_service.set_boxer(db, user, payload.user_card_id)


@router.put("/nickname", response_model=MordoboiBoxerOut)
async def set_nickname(
    payload: MordoboiNicknameRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await mordoboi_service.set_nickname(db, user, payload.nickname)


@router.get("/legend", response_model=MordoboiLegendOut)
async def get_legend(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_legend(db, user)


@router.post("/legend/start", response_model=MordoboiMatchOut)
async def start_legend(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"mordoboi_legend:{user.id}", max_calls=20, window_seconds=60)
    return await mordoboi_service.start_legend(db, user)


@router.get("/club-ring", response_model=MordoboiClubRingOut)
async def get_club_ring(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_club_ring(db, user)


@router.post("/matches/bot", response_model=MordoboiMatchOut)
async def create_bot_match(
    payload: MordoboiBotMatchRequest | None = None,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"mordoboi_bot_match:{user.id}", max_calls=15, window_seconds=60)
    return await mordoboi_service.create_bot_match(db, user, (payload or MordoboiBotMatchRequest()).difficulty)


@router.post("/matches/challenge", response_model=MordoboiMatchOut)
async def create_challenge(
    payload: MordoboiChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"mordoboi_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await mordoboi_service.create_challenge(db, user, payload.receiver_id)


@router.post("/matches/open-challenge", response_model=MordoboiMatchOut)
async def create_open_challenge(
    payload: MordoboiOpenChallengeRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    await check_rate_limit(f"mordoboi_open_challenge:{user.id}", max_calls=10, window_seconds=60)
    return await mordoboi_service.create_open_challenge(db, user, payload.stake_coins)


@router.get("/matches/open/{match_id}", response_model=MordoboiOpenChallengePreviewOut)
async def preview_open_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.preview_open_challenge(db, user, match_id)


@router.post("/matches/open/{match_id}/accept", response_model=MordoboiMatchOut)
async def accept_open_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.accept_open_challenge(db, user, match_id)


@router.post("/matches/{match_id}/accept", response_model=MordoboiMatchOut)
async def accept_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.accept_challenge(db, user, match_id)


@router.post("/matches/{match_id}/decline", response_model=MordoboiMatchOut)
async def decline_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.decline_challenge(db, user, match_id)


@router.post("/matches/{match_id}/cancel", response_model=MordoboiMatchOut)
async def cancel_challenge(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.cancel_challenge(db, user, match_id)


@router.post("/matches/{match_id}/forfeit", response_model=MordoboiMatchOut)
async def forfeit_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.forfeit_match(db, user, match_id)


@router.post("/matches/{match_id}/pick", response_model=MordoboiMatchOut)
async def submit_pick(
    match_id: int, payload: MordoboiPickRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"mordoboi_pick:{user.id}", max_calls=120, window_seconds=60)
    return await mordoboi_service.submit_pick(db, user, match_id, payload.action, payload.version)


@router.post("/matches/{match_id}/brutality", response_model=MordoboiMatchOut)
async def apply_brutality(
    match_id: int, payload: MordoboiBrutalityRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await mordoboi_service.apply_brutality(db, user, match_id, payload.cosmetic_id)


@router.get("/matches", response_model=list[MordoboiMatchOut])
async def list_matches(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.list_matches(db, user)


@router.get("/matches/{match_id}", response_model=MordoboiMatchOut)
async def get_match(match_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await mordoboi_service.get_match(db, user, match_id)


@router.post("/matchmaking/search", response_model=MordoboiSearchStatusOut)
async def start_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"mordoboi_search:{user.id}", max_calls=10, window_seconds=60)
    await mordoboi_service.start_search(db, user)
    return MordoboiSearchStatusOut(status="searching", match_id=None)


@router.get("/matchmaking/status", response_model=MordoboiSearchStatusOut)
async def get_search_status(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    status, match_id = await mordoboi_service.get_search_status(db, user)
    return MordoboiSearchStatusOut(status=status, match_id=match_id)


@router.post("/matchmaking/cancel", status_code=204)
async def cancel_search(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await mordoboi_service.cancel_search(db, user)
