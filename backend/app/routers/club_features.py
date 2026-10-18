"""Club emblem constructor and «Казна за Stars» (club_emblem_service /
club_treasury_service). Separate from routers/clubs.py only to keep that
file from growing further; same /clubs prefix, all under /clubs/me/."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.club_emblem import ClubDonationInvoiceIn, ClubEmblemStateOut, ClubEmblemUpdateIn, ClubTreasuryOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import club_emblem_service, club_treasury_service, shop_product_service

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
