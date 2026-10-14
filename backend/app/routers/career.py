from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.career import (
    CareerCreateIn,
    CareerInviteResponseIn,
    CareerLineupIn,
    CareerMatchEventsOut,
    CareerPlanIn,
    CareerRolesIn,
    CareerMarkingIn,
    CareerHalftimeIn,
    CareerTacticPreviewIn,
    CareerAmbitionIn,
    CareerTrainingIn,
    CareerCupIn,
    CareerSquadIn,
    CareerCampIn,
    CareerViewOut,
)
from app.services import career_service

router = APIRouter(prefix="/career", tags=["career"])


async def _view(db: AsyncSession, user: User) -> dict:
    view = await career_service.get_view(db, user)
    view["invite"] = await career_service.pending_invite(db, user.id)
    return view


@router.get("", response_model=CareerViewOut)
async def get_career(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """The current season (rounds whose time has come are played first)."""
    return await _view(db, user)


@router.post("/seasons", response_model=CareerViewOut)
async def create_season(payload: CareerCreateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"career_create:{user.id}", max_calls=5, window_seconds=60)
    await career_service.create_season(db, user, payload.difficulty, payload.friend_id)
    return await _view(db, user)


@router.post("/seasons/{season_id}/invite", response_model=CareerViewOut)
async def respond_invite(
    season_id: int, payload: CareerInviteResponseIn,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    await career_service.respond_invite(db, user, season_id, payload.accept)
    return await _view(db, user)


@router.post("/seasons/{season_id}/start", response_model=CareerViewOut)
async def start_without_friend(season_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.start_without_friend(db, user, season_id)
    return await _view(db, user)


@router.put("/lineup", response_model=CareerViewOut)
async def set_lineup(payload: CareerLineupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.set_lineup(
        db, user, payload.slots, payload.formation, payload.mentality, payload.playstyle, payload.round_index,
        payload.tactic,
    )
    return await _view(db, user)


@router.put("/plan", response_model=CareerViewOut)
async def set_plan(payload: CareerPlanIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Match plan for the coming rounds: up to N conditional instructions
    (score + minute -> mentality/style) and N substitutions."""
    await career_service.set_plan(db, user, payload.rules, payload.subs, payload.round_index, payload.set_pieces)
    return await _view(db, user)


@router.put("/roles", response_model=CareerViewOut)
async def set_roles(payload: CareerRolesIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Player roles per line: wingers, holding midfielder, full-backs."""
    await career_service.set_roles(db, user, payload.roles, payload.round_index)
    return await _view(db, user)


@router.put("/marking", response_model=CareerViewOut)
async def set_marking(payload: CareerMarkingIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Man-mark the next opponent's star (next round only)."""
    await career_service.set_marking(db, user, payload.marker_card_id, payload.round_index)
    return await _view(db, user)


@router.put("/halftime", response_model=CareerViewOut)
async def set_halftime(payload: CareerHalftimeIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Live match centre: orders for the second half while the break lasts."""
    await check_rate_limit(f"career_halftime:{user.id}", max_calls=20, window_seconds=60)
    await career_service.set_halftime(db, user, payload.model_dump())
    return await _view(db, user)


@router.put("/ambition", response_model=CareerViewOut)
async def set_ambition(payload: CareerAmbitionIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Board objective for the season (before round 1)."""
    await career_service.set_ambition(db, user, payload.ambition)
    return await _view(db, user)


@router.put("/training", response_model=CareerViewOut)
async def set_training(payload: CareerTrainingIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Training focus before the next round (kept until changed)."""
    await career_service.set_training(db, user, payload.training, payload.round_index)
    return await _view(db, user)


@router.put("/cup", response_model=CareerViewOut)
async def set_cup(payload: CareerCupIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Cup rotation: the freshest players in cup ties instead of the league XI."""
    await career_service.set_cup_rotation(db, user, payload.rotation)
    return await _view(db, user)


@router.get("/seasons/{season_id}/cup/{round_index}/{tie_index}", response_model=CareerMatchEventsOut)
async def cup_match(
    season_id: int, round_index: int, tie_index: int,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await career_service.cup_match_events(db, user, season_id, round_index, tie_index)


@router.put("/squad", response_model=CareerViewOut)
async def set_squad(payload: CareerSquadIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Season squad (заявка) before round 1 — the off-season core decides
    how much familiarity carries over."""
    await career_service.set_squad(db, user, payload.card_ids)
    return await _view(db, user)


@router.put("/camp", response_model=CareerViewOut)
async def set_camp(payload: CareerCampIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.set_camp(db, user, payload.camp)
    return await _view(db, user)


@router.post("/friendly", response_model=CareerViewOut)
async def play_friendly(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """One free friendly before round 1 (no rewards, fatigue or familiarity)."""
    await check_rate_limit(f"career_friendly:{user.id}", max_calls=5, window_seconds=60)
    await career_service.play_friendly(db, user)
    return await _view(db, user)


@router.get("/seasons/{season_id}/friendly", response_model=CareerMatchEventsOut)
async def friendly_events(season_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await career_service.friendly_events(db, user, season_id)


@router.get("/collection")
async def career_collection(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Own usable cards for building the season squad."""
    return await career_service.collection(db, user)


@router.get("/leaderboard")
async def career_leaderboard(
    division: int | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """Coaches by reputation: overall or within one division."""
    return await career_service.leaderboard(db, user, division)


@router.post("/tactics/preview")
async def preview_tactic(
    payload: CareerTacticPreviewIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """Matchup report for a tactic being chosen (not saved) vs the next
    opponent — the same interaction table the engine applies."""
    return {"matchup": await career_service.preview(db, user, payload.tactic)}


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await career_service.leave_season(db, user)


@router.get("/seasons/{season_id}/rounds/{round_index}/matches/{match_index}", response_model=CareerMatchEventsOut)
async def match_events(
    season_id: int, round_index: int, match_index: int,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await career_service.match_events(db, user, season_id, round_index, match_index)
