from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.user import User
from app.schemas.card import CollectionStatsOut
from app.schemas.collection import (
    BulkSellRequest,
    CollectionFilterParams,
    SellCardRequest,
    SellResultOut,
    UserCardListItem,
)
from app.services.collection_service import collection_stats, list_user_cards, sell_cards

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("/cards", response_model=Page[UserCardListItem])
async def get_my_cards(
    filters: CollectionFilterParams = Depends(),
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_user_cards(db, user.id, filters, params)


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
