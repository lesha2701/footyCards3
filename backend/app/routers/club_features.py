"""Club emblem constructor, «Казна за Stars» and «Лишние карты»
(club_emblem_service / club_treasury_service / club_market_service).
Separate from routers/clubs.py only to keep that file from growing
further; same /clubs prefix, all under /clubs/me/."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.rate_limit import check_rate_limit
from app.database import get_db
from app.models.user import User
from app.schemas.club import BudgetPolicyIn, ClubDetailOut, MemberRoleIn
from app.schemas.club_emblem import ClubDonationInvoiceIn, ClubEmblemStateOut, ClubEmblemUpdateIn, ClubTreasuryOut
from app.schemas.club_quest import ClubQuestsOut
from app.schemas.club_trophy import ClubTrophiesOut
from app.schemas.club_war import ClubWarOut
from app.schemas.club_reward import ClubShopOut
from app.schemas.club_wall import ClubPostIn, ClubWallOut
from app.schemas.monetization import GrantedRewardsOut
from app.schemas.club_market import ClubSurplusOut, SurplusCardIdsIn, SurplusSellOut
from app.schemas.club_pack_open import ClubPackOpenResult
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import (
    club_emblem_service,
    club_market_service,
    club_quest_service,
    club_reward_service,
    club_service,
    club_shop_service,
    club_treasury_service,
    club_trophy_service,
    club_wall_service,
    club_war_service,
    shop_product_service,
)

router = APIRouter(prefix="/clubs", tags=["clubs"])


@router.get("/me/emblem", response_model=ClubEmblemStateOut)
async def get_emblem(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_emblem_service.get_state(db, user)


@router.put("/me/emblem", response_model=ClubEmblemStateOut)
async def update_emblem(payload: ClubEmblemUpdateIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_emblem_service.update_emblem(db, user, payload)


@router.post("/me/emblem/items/{item_id}/buy", response_model=ClubEmblemStateOut)
async def buy_emblem_item(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_emblem_service.buy_with_budget(db, user, item_id)


@router.post("/me/emblem/items/{item_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def emblem_item_invoice(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await club_emblem_service.stars_order(db, user, item_id))


@router.get("/me/treasury", response_model=ClubTreasuryOut)
async def get_treasury(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_treasury_service.get_treasury(db, user)


@router.post("/me/treasury/stars-invoice", response_model=StarsInvoiceCreateOut)
async def treasury_invoice(payload: ClubDonationInvoiceIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await club_treasury_service.stars_order(db, user, payload.stars, payload.target))


@router.get("/me/surplus", response_model=ClubSurplusOut)
async def get_surplus(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_market_service.get_surplus(db, user)


@router.post("/me/surplus/sell", response_model=SurplusSellOut)
async def sell_surplus(payload: SurplusCardIdsIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_market_service.sell_cards(db, user, payload.card_ids)


@router.post("/me/surplus/exchange", response_model=ClubPackOpenResult)
async def exchange_surplus(payload: SurplusCardIdsIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_market_service.exchange_cards(db, user, payload.card_ids)


@router.post("/me/members/{user_id}/role", response_model=ClubDetailOut)
async def set_member_role(
    user_id: int, payload: MemberRoleIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_service.set_member_role(db, user, user_id, payload.role)


@router.put("/me/budget-policy", response_model=ClubDetailOut)
async def set_budget_policy(payload: BudgetPolicyIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_service.set_budget_policy(db, user, payload.treasurer_only)


@router.get("/me/wall", response_model=ClubWallOut)
async def get_wall(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_wall_service.get_wall(db, user)


@router.post("/me/wall", response_model=ClubWallOut)
async def create_wall_post(payload: ClubPostIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await check_rate_limit(f"club_wall_post:{user.id}", max_calls=6, window_seconds=60)
    return await club_wall_service.create_post(db, user, payload.text, payload.announce)


@router.delete("/me/wall/{post_id}", response_model=ClubWallOut)
async def delete_wall_post(post_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_wall_service.delete_post(db, user, post_id)


@router.post("/me/wall/{post_id}/pin", response_model=ClubWallOut)
async def pin_wall_post(post_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_wall_service.toggle_pin(db, user, post_id)


@router.get("/me/shop", response_model=ClubShopOut)
async def get_shop(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_shop_service.get_shop(db, user)


@router.post("/me/shop/{item_id}/buy", response_model=ClubShopOut)
async def buy_shop_item(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_shop_service.buy(db, user, item_id)


@router.post("/me/rewards/{grant_id}/claim", response_model=GrantedRewardsOut)
async def claim_club_reward(grant_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_reward_service.claim(db, user, grant_id)


@router.get("/me/quests", response_model=ClubQuestsOut)
async def get_quests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_quest_service.get_quests(db, user)


@router.get("/{club_id}/trophies", response_model=ClubTrophiesOut)
async def get_trophies(club_id: int, db: AsyncSession = Depends(get_db), _user: User = Depends(get_current_user)):
    return await club_trophy_service.get_trophies(db, club_id)


@router.get("/me/war", response_model=ClubWarOut)
async def get_war(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_war_service.get_war(db, user)


@router.post("/me/emblem/items/{item_id}/buy-club-stars", response_model=ClubEmblemStateOut)
async def buy_emblem_item_club_stars(item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_emblem_service.buy_with_club_stars(db, user, item_id)
