from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.player_career import (
    PlayerCareerContractIn,
    PlayerCareerCounterIn,
    PlayerCareerEventIn,
    PlayerCareerFriendsCreateIn,
    PlayerCareerFriendsRespondIn,
    PlayerCareerMomentIn,
    PlayerCareerStartIn,
    PlayerCareerViewOut,
)
from app.services import player_career_friends, player_career_life, player_career_service, player_career_shop
from app.services.game_config_service import get_config

router = APIRouter(prefix="/player-career", tags=["player-career"])


@router.get("", response_model=PlayerCareerViewOut)
async def get_player_career(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Clubs, contract, the current/last season (due rounds are played first)."""
    return await player_career_service.get_view(db, user)


@router.post("/contract", response_model=PlayerCareerViewOut)
async def sign_contract(payload: PlayerCareerContractIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"player_career_contract:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_service.sign_contract(db, user, payload.club_key)


@router.post("/seasons", response_model=PlayerCareerViewOut)
async def start_season(
    payload: PlayerCareerStartIn | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"player_career_season:{user.id}", max_calls=5, window_seconds=60)
    return await player_career_service.start_season(db, user, fast=bool(payload and payload.fast))


@router.post("/leave", response_model=PlayerCareerViewOut)
async def leave_season(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_career_service.leave_season(db, user)


@router.post("/offers/{club_key}/accept", response_model=PlayerCareerViewOut)
async def accept_offer(club_key: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Transfer window: sign the offer (salary + signing bonus)."""
    await check_rate_limit(f"player_career_offer:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_service.accept_offer(db, user, club_key)


@router.post("/offers/{club_key}/counter", response_model=PlayerCareerViewOut)
async def counter_offer(
    club_key: str, payload: PlayerCareerCounterIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """Transfer window: ask for more — the club may agree or walk away."""
    await check_rate_limit(f"player_career_offer:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_service.counter_offer(db, user, club_key, payload.raise_pct)


@router.post("/moments/{moment_index}", response_model=PlayerCareerViewOut)
async def play_moment(
    moment_index: int, payload: PlayerCareerMomentIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """A decision in a key moment of the pending match."""
    await check_rate_limit(f"player_career_moment:{user.id}", max_calls=20, window_seconds=60)
    return await player_career_service.play_moment(db, user, moment_index, payload.option, payload.hit)


@router.post("/events/{event_id}", response_model=PlayerCareerViewOut)
async def answer_event(
    event_id: int, payload: PlayerCareerEventIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"player_career_event:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_service.answer_event(db, user, event_id, payload.choice)


@router.post("/chest")
async def open_chest(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The daily career chest: coins, sometimes a skill token."""
    await check_rate_limit(f"player_career_chest:{user.id}", max_calls=5, window_seconds=60)
    return await player_career_life.open_chest(db, user, await get_config(db))


@router.post("/weekly/{code}/claim", response_model=PlayerCareerViewOut)
async def claim_weekly(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"player_career_weekly:{user.id}", max_calls=10, window_seconds=60)
    await player_career_life.claim_weekly(db, user, code, await get_config(db))
    return await player_career_service.get_view(db, user)


@router.get("/rankings")
async def get_rankings(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """This week's scorers and ratings, the prestige top."""
    return await player_career_life.rankings(db, user)


@router.post("/shop/{code}", response_model=PlayerCareerViewOut)
async def buy_with_coins(code: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Full freshness (refresh) or healing (heal) for coins."""
    await check_rate_limit(f"player_career_shop:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_shop.buy_with_coins(db, user, code)


@router.get("/friends")
async def get_friends_league(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_career_friends.view(db, user)


@router.post("/friends")
async def create_friends_league(
    payload: PlayerCareerFriendsCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"player_career_friends:{user.id}", max_calls=5, window_seconds=60)
    return await player_career_friends.create(db, user, payload.invite_ids)


@router.post("/friends/{league_id}/respond")
async def respond_friends_league(
    league_id: int, payload: PlayerCareerFriendsRespondIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await check_rate_limit(f"player_career_friends:{user.id}", max_calls=10, window_seconds=60)
    return await player_career_friends.respond(db, user, league_id, payload.accept)


@router.post("/friends/{league_id}/start")
async def start_friends_league(league_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"player_career_friends:{user.id}", max_calls=5, window_seconds=60)
    return await player_career_friends.start(db, user, league_id)


@router.post("/friends/{league_id}/cancel")
async def cancel_friends_league(league_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_career_friends.cancel(db, user, league_id)
