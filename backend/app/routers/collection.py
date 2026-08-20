from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.enums import Rarity
from app.models.user import User
from app.schemas.card import CollectionStatsOut, UserCardOut
from app.schemas.card_upgrade import CardUpgradeResultOut, CardUpgradeRuleOut, UpgradeCardRequest
from app.schemas.collection import (
    AlbumCollectionDetailOut,
    AlbumOverviewOut,
    BulkSellRequest,
    CollectionFilterParams,
    SellCardRequest,
    SellResultOut,
    SetCardHiddenRequest,
    UserCardListItem,
)
from app.services.card_upgrade_service import list_rules, list_upgradeable_cards, upgrade_card
from app.services.collection_service import (
    collection_stats,
    get_album_collection_detail,
    get_album_overview,
    list_user_cards,
    sell_cards,
    set_card_hidden,
)

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("/album", response_model=AlbumOverviewOut)
async def get_album_overview_route(
    search: Optional[str] = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await get_album_overview(db, user.id, search)


@router.get("/album/{collection_id}", response_model=AlbumCollectionDetailOut)
async def get_album_collection_detail_route(
    collection_id: int, search: Optional[str] = None, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await get_album_collection_detail(db, user.id, collection_id, search)


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


@router.get("/upgrade-cards", response_model=list[UserCardOut])
async def get_upgradeable_cards(
    rarity: Rarity, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await list_upgradeable_cards(db, user.id, rarity)


@router.post("/upgrade", response_model=CardUpgradeResultOut)
async def upgrade_my_cards(
    payload: UpgradeCardRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await upgrade_card(db, user, payload.user_card_ids, payload.to_rarity, payload.idempotency_key)
