from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.pagination import Page, PageParams
from app.database import get_db
from app.models.enums import Rarity
from app.models.user import User
from app.schemas.card import CollectionStatsOut, UserCardOut
from app.schemas.card_star import CardStarClaimRequest, CardStarFeedRequest, CardStarOperationOut, CardStarStateOut
from app.schemas.card_upgrade import CardUpgradeResultOut, CardUpgradeRuleOut, UpgradeCardRequest
from app.schemas.collection import (
    CardFilterDefault,
    CardFilterOptionsOut,
    SetCardsLockedOut,
    SetCardsLockedRequest,
    AlbumCollectionDetailOut,
    AlbumOverviewOut,
    BulkSellRequest,
    CollectionFilterParams,
    SellCardRequest,
    SellDuplicatesOut,
    SellDuplicatesRequest,
    SellResultOut,
    SetCardHiddenRequest,
    UserCardListItem,
)
from app.schemas.diamond_upgrade import (
    DiamondMaterialCardsOut,
    DiamondRatingCapOut,
    DiamondUpgradeTierOut,
    FeedCardsRequest,
    FeedCardsResult,
)
from app.services import card_star_service
from app.services.card_upgrade_service import list_rules, list_upgradeable_cards, upgrade_card
from app.services.collection_service import (
    collection_stats,
    get_album_collection_detail,
    get_album_overview,
    list_user_cards,
    sell_cards,
    sell_duplicates,
    set_card_hidden,
)
from app.services.diamond_upgrade_service import feed_cards, get_effective_rating_cap, get_material_cards, list_tiers

router = APIRouter(prefix="/collection", tags=["collection"])


@router.get("/cards/{card_id}/stars", response_model=CardStarStateOut)
async def get_card_stars(card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await card_star_service.get_state(db, user, card_id)


@router.post("/cards/{card_id}/stars/feed", response_model=CardStarOperationOut)
async def feed_card_stars(
    card_id: int, payload: CardStarFeedRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await card_star_service.feed(db, user, card_id, payload)


@router.post("/cards/{card_id}/stars/claim", response_model=CardStarOperationOut)
async def claim_card_star(
    card_id: int, payload: CardStarClaimRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await card_star_service.claim(db, user, card_id, payload.idempotency_key)


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


@router.patch("/cards/lock", response_model=SetCardsLockedOut)
async def set_cards_locked(
    payload: SetCardsLockedRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    """The owner's «замок»: a locked copy can't be sold or burned as material."""
    from app.services.collection_service import set_cards_user_locked

    ids = await set_cards_user_locked(db, user, payload.card_ids, payload.locked)
    return SetCardsLockedOut(card_ids=ids, locked=payload.locked)


@router.get("/filter-options", response_model=CardFilterOptionsOut)
async def get_filter_options(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.collection_service import card_filter_options

    return await card_filter_options(db, user.id)


@router.get("/filter-default", response_model=Optional[CardFilterDefault])
async def get_filter_default(user: User = Depends(get_current_user)):
    return user.card_filter_default


@router.put("/filter-default", response_model=Optional[CardFilterDefault])
async def put_filter_default(
    payload: Optional[CardFilterDefault] = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """Saves the default filter (null / empty clears it)."""
    from app.services.collection_service import save_filter_default

    return await save_filter_default(db, user, payload.model_dump(exclude_none=True) if payload else None)


@router.get("/stats", response_model=CollectionStatsOut)
async def get_my_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await collection_stats(db, user.id)


@router.post("/cards/sell", response_model=SellResultOut)
async def sell_one_card(
    payload: SellCardRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await sell_cards(db, user, [payload.user_card_id], payload.confirm_last_copy, payload.confirm_skill_loss)


@router.post("/cards/sell-duplicates", response_model=SellDuplicatesOut)
async def sell_duplicate_cards(
    payload: SellDuplicatesRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await sell_duplicates(db, user, payload.preview, payload.include_diamond, payload.include_star_material)


@router.post("/cards/bulk-sell", response_model=SellResultOut)
async def sell_many_cards(
    payload: BulkSellRequest, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await sell_cards(db, user, payload.user_card_ids, payload.confirm_last_copy, payload.confirm_skill_loss)


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
    return await upgrade_card(
        db, user, payload.user_card_ids, payload.to_rarity, payload.idempotency_key, payload.confirm_skill_loss,
        confirm_leave_squad=payload.confirm_leave_squad,
    )


@router.get("/diamond-upgrade-tiers", response_model=list[DiamondUpgradeTierOut])
async def get_diamond_upgrade_tiers(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await list_tiers(db)


@router.get("/diamond-upgrade-cap", response_model=DiamondRatingCapOut)
async def get_diamond_upgrade_cap(db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return DiamondRatingCapOut(cap=await get_effective_rating_cap(db))


@router.get("/diamond-upgrade/material-cards", response_model=DiamondMaterialCardsOut)
async def get_diamond_material_cards_route(
    diamond_card_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await get_material_cards(db, user.id, diamond_card_id)


@router.post("/diamond-upgrade/feed", response_model=FeedCardsResult)
async def feed_diamond_card(
    payload: FeedCardsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await feed_cards(db, user, payload.diamond_card_id, payload.material_card_ids, payload.confirm_skill_loss)
