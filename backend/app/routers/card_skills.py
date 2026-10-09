from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.card_skill import CardSkillLedger
from app.models.user import User
from app.schemas.card_skill import (
    CardSkillStateOut,
    SkillCatalogOut,
    SkillLedgerEntryOut,
    SkillOperationOut,
    SkillOperationRequest,
    SkillTokensOut,
)
from app.services import card_skill_service

router = APIRouter(prefix="/card-skills", tags=["card-skills"])


@router.get("/catalog", response_model=SkillCatalogOut)
async def get_catalog(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await card_skill_service.get_catalog(db)


@router.get("/tokens", response_model=SkillTokensOut)
async def get_my_tokens(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    balances = await card_skill_service.get_token_balances(db, user.id)
    return SkillTokensOut(tokens=card_skill_service.balances_out(balances))


@router.get("/cards/{card_id}", response_model=CardSkillStateOut)
async def get_card_skill_state(card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await card_skill_service.get_card_state(db, user, card_id)


@router.post("/cards/{card_id}", response_model=SkillOperationOut)
async def change_card_skill(
    card_id: int, payload: SkillOperationRequest,
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await card_skill_service.perform_operation(db, user, card_id, payload, payload.idempotency_key)


@router.get("/history", response_model=list[SkillLedgerEntryOut])
async def get_my_history(
    limit: int = Query(50, ge=1, le=200), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CardSkillLedger).where(CardSkillLedger.user_id == user.id)
        .order_by(CardSkillLedger.created_at.desc(), CardSkillLedger.id.desc()).limit(limit)
    )
    return result.scalars().all()
