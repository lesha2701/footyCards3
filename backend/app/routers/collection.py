from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.user import User
from app.schemas.card import CollectionStatsOut
from app.schemas.card_upgrade import CardUpgradeResultOut, CardUpgradeRuleOut, UpgradeCardRequest
from app.schemas.collection import (
    BulkSellRequest,
    CollectionFilterParams,
    SellCardRequest,
    SellResultOut,
    SetCardHiddenRequest,
    UserCardListItem,
)
from app.services.card_upgrade_service import list_rules, upgrade_card
from app.services.collection_service import collection_stats, list_user_cards, sell_cards, set_card_hidden

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("/cards", response_model=Page[UserCardListItem])
async def get_my_cards(
    filters: CollectionFilterParams = Depends(),
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_user_cards(db, user.id, filters, params)


@router.patch("/cards/{card_id}/hidden", response_model=UserCardListItem)
async def set_card_hidden_from_trade(
    card_id: int, payload: SetCardHiddenRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await set_card_hidden(db, user.id, card_id, payload.hidden)


@router.get("/stats", response_model=CollectionStatsOut)
async def get_my_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await collection_stats(db, user.id)


@router.post("/cards/sell", response_model=SellResultOut)
async def sell_one_card(
    payload: SellCardRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await sell_cards(db, user, [payload.user_card_id], payload.confirm_last_copy)


@router.post("/cards/bulk-sell", response_model=SellResultOut)
async def sell_many_cards(
    payload: BulkSellRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await sell_cards(db, user, payload.user_card_ids, payload.confirm_last_copy)


@router.get("/upgrade-rules", response_model=list[CardUpgradeRuleOut])
async def get_upgrade_rules(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await list_rules(db)


@router.post("/cards/{card_id}/upgrade", response_model=CardUpgradeResultOut)
async def upgrade_my_card(
    card_id: int,
    payload: UpgradeCardRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await upgrade_card(db, user, card_id, payload.to_rarity, payload.idempotency_key)
