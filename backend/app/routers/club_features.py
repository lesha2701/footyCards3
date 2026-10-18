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
from app.schemas.club_wall import ClubPostIn, ClubWallOut
from app.schemas.club_market import ClubSurplusOut, SurplusCardIdsIn, SurplusExchangeOut, SurplusSellOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import (
    club_emblem_service,
    club_market_service,
    club_service,
    club_treasury_service,
    club_wall_service,
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
    return await shop_product_service.create_invoice(db, user, *await club_treasury_service.stars_order(db, user, payload.stars))


@router.get("/me/surplus", response_model=ClubSurplusOut)
async def get_surplus(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_market_service.get_surplus(db, user)


@router.post("/me/surplus/sell", response_model=SurplusSellOut)
async def sell_surplus(payload: SurplusCardIdsIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_market_service.sell_cards(db, user, payload.card_ids)


@router.post("/me/surplus/exchange", response_model=SurplusExchangeOut)
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
