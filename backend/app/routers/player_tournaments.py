from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.pack import UserCoachCardOut
from app.schemas.personal_squad import (
    PersonalSquadCoachRequest, PersonalSquadOut, PersonalSquadRenameRequest, PersonalSquadSetRequest,
    PersonalSquadTacticsRequest,
)
from app.schemas.player_tournament import (
    PlayerTournamentApplyResult, PlayerTournamentCurrentOut, PlayerTournamentDetailOut,
    PlayerTournamentMatchDetailOut, TournamentRatingRowOut,
)
from app.services import (
    personal_squad_service, player_tournament_query_service, player_tournament_queue_service,
)
from app.services.lineup_service import list_user_coach_cards

router = APIRouter(prefix="/player-tournaments", tags=["player-tournaments"])


@router.get("/squads", response_model=list[PersonalSquadOut])
async def read_squads(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await personal_squad_service.list_templates(db, user)


@router.get("/squads/coach-cards", response_model=list[UserCoachCardOut])
async def read_coach_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_user_coach_cards(db, user)


@router.put("/squads/{template_index}/cards", response_model=PersonalSquadOut)
async def update_squad_cards(
    template_index: int, payload: PersonalSquadSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_squad_cards(db, user, payload, template_index)


@router.put("/squads/{template_index}/tactics", response_model=PersonalSquadOut)
async def update_squad_tactics(
    template_index: int, payload: PersonalSquadTacticsRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_tactics(db, user, payload, template_index)


@router.put("/squads/{template_index}/coach", response_model=PersonalSquadOut)
async def update_squad_coach(
    template_index: int, payload: PersonalSquadCoachRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.set_coach(db, user, payload, template_index)


@router.put("/squads/{template_index}/name", response_model=PersonalSquadOut)
async def rename_squad(
    template_index: int, payload: PersonalSquadRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.rename_template(db, user, template_index, payload.name)


@router.post("/squads/{template_index}/activate", response_model=PersonalSquadOut)
async def activate_squad(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await personal_squad_service.activate_template(db, user, template_index)


@router.post("/apply", response_model=PlayerTournamentApplyResult)
async def apply(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_tournament_queue_service.apply_to_tournament(db, user)


@router.get("/current", response_model=PlayerTournamentCurrentOut)
async def current(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await player_tournament_queue_service.get_current(db, user)


@router.get("/rating", response_model=list[TournamentRatingRowOut])
async def rating(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_rating_leaderboard(db)


@router.get("/matches/{match_id}", response_model=PlayerTournamentMatchDetailOut)
async def match_detail(match_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_match_detail(db, match_id)


@router.get("/{tournament_id}", response_model=PlayerTournamentDetailOut)
async def tournament_detail(tournament_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await player_tournament_query_service.get_tournament_detail(db, tournament_id)
