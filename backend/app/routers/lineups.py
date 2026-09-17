from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.lineup import (
    LineupCoachSetRequest, LineupOut, LineupRenameRequest, LineupSetRequest, LineupTacticRequest, UserCoachCardOut,
)
from app.services.lineup_service import (
    activate_template, get_active_lineup, list_templates, list_user_coach_cards, rename_template,
    set_lineup, set_lineup_coach, set_tactic,
)

router = APIRouter(prefix="/lineups", tags=["lineups"])


@router.get("/active", response_model=LineupOut)
async def read_active_lineup(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await get_active_lineup(db, user)


@router.get("/coach-cards", response_model=list[UserCoachCardOut])
async def read_user_coach_cards(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_user_coach_cards(db, user)


@router.put("/active", response_model=LineupOut)
async def update_active_lineup(
    payload: LineupSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup(db, user, payload)


@router.post("/tactic", response_model=LineupOut)
async def update_tactic(
    payload: LineupTacticRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_tactic(db, user, payload.tactic)


@router.put("/coach", response_model=LineupOut)
async def update_lineup_coach(
    payload: LineupCoachSetRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_lineup_coach(db, user, payload)


@router.get("/templates", response_model=list[LineupOut])
async def read_templates(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await list_templates(db, user)


@router.put("/templates/{template_index}", response_model=LineupOut)
async def update_template(
    template_index: int, payload: LineupSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_lineup(db, user, payload, template_index)


@router.post("/templates/{template_index}/tactic", response_model=LineupOut)
async def update_template_tactic(
    template_index: int, payload: LineupTacticRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_tactic(db, user, payload.tactic, template_index)


@router.put("/templates/{template_index}/coach", response_model=LineupOut)
async def update_template_coach(
    template_index: int, payload: LineupCoachSetRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await set_lineup_coach(db, user, payload, template_index)


@router.put("/templates/{template_index}/name", response_model=LineupOut)
async def update_template_name(
    template_index: int, payload: LineupRenameRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await rename_template(db, user, template_index, payload.name)


@router.post("/templates/{template_index}/activate", response_model=LineupOut)
async def activate_template_route(
    template_index: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await activate_template(db, user, template_index)
