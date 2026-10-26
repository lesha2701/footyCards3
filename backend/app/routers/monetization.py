from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.monetization import (
    ArtifactEquipIn,
    ArtifactGiftIn,
    ClubPassOut,
    CosmeticCatalogOut,
    CosmeticEquipIn,
    GrantedRewardsOut,
    SeasonClaimIn,
    SeasonPassOut,
    ShopInvoiceStatusOut,
    StarterOfferOut,
)
from app.schemas.stars import StarsInvoiceCreateOut
from app.services import (
    artifact_service,
    club_pass_service,
    cosmetic_service,
    season_pass_service,
    shop_product_service,
    starter_offer_service,
)

router = APIRouter(tags=["monetization"])


class AutoRenewIn(BaseModel):
    auto_renew: bool


# --- cosmetics ------------------------------------------------------------------------


@router.get("/cosmetics", response_model=CosmeticCatalogOut)
async def cosmetics(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await club_pass_service.expire_if_needed(db, user)
    return await cosmetic_service.catalog(db, user)


@router.post("/cosmetics/{cosmetic_id}/buy", response_model=CosmeticCatalogOut)
async def buy_cosmetic(cosmetic_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await cosmetic_service.buy_with_coins(db, user, cosmetic_id)


@router.post("/cosmetics/{cosmetic_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def cosmetic_invoice(cosmetic_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await cosmetic_service.stars_order(db, user, cosmetic_id))


@router.post("/cosmetics/equip", response_model=CosmeticCatalogOut)
async def equip_cosmetic(payload: CosmeticEquipIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await cosmetic_service.equip(db, user, payload.kind, payload.cosmetic_id)


# --- «Клубный абонемент» --------------------------------------------------------------


@router.get("/club-pass", response_model=ClubPassOut)
async def club_pass(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_pass_service.get_status(db, user)


@router.post("/club-pass/stars-invoice", response_model=StarsInvoiceCreateOut)
async def club_pass_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await club_pass_service.stars_order(db, user))


@router.post("/club-pass/daily", response_model=GrantedRewardsOut)
async def club_pass_daily(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await club_pass_service.claim_daily(db, user)


@router.post("/club-pass/auto-renew", response_model=ClubPassOut)
async def club_pass_auto_renew(
    payload: AutoRenewIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await club_pass_service.set_auto_renew(db, user, payload.auto_renew)


# --- «Сезонный пропуск» --------------------------------------------------------------


@router.get("/season-pass", response_model=SeasonPassOut)
async def season_pass(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await season_pass_service.get_pass(db, user)


@router.post("/season-pass/claim", response_model=GrantedRewardsOut)
async def season_claim(payload: SeasonClaimIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await season_pass_service.claim(db, user, payload.level, payload.track)


@router.post("/season-pass/stars-invoice", response_model=StarsInvoiceCreateOut)
async def season_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await season_pass_service.stars_order(db, user))


# --- starter offer --------------------------------------------------------------------


@router.get("/starter-offer", response_model=StarterOfferOut)
async def starter_offer(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await starter_offer_service.get_status(db, user)


@router.post("/starter-offer/seen", response_model=StarterOfferOut)
async def starter_offer_seen(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await starter_offer_service.mark_seen(db, user)


@router.post("/starter-offer/stars-invoice", response_model=StarsInvoiceCreateOut)
async def starter_offer_invoice(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await starter_offer_service.stars_order(db, user))


# --- «Артефакты» ----------------------------------------------------------------------


@router.get("/artifacts")
async def artifacts(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await artifact_service.catalog(db, user)


@router.post("/artifacts/{artifact_id}/buy")
async def buy_artifact(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await artifact_service.buy_with_coins(db, user, artifact_id)


@router.post("/artifacts/{artifact_id}/stars-invoice", response_model=StarsInvoiceCreateOut)
async def artifact_invoice(artifact_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.create_invoice(db, user, *await artifact_service.stars_order(db, user, artifact_id))


@router.post("/artifacts/{artifact_id}/gift-invoice", response_model=StarsInvoiceCreateOut)
async def artifact_gift_invoice(
    artifact_id: int, payload: ArtifactGiftIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    """A copy bought with Stars straight for a friend."""
    return await shop_product_service.create_invoice(
        db, user, *await artifact_service.stars_gift_order(db, user, artifact_id, payload.recipient_id),
    )


@router.post("/artifacts/copies/{copy_id}/active")
async def activate_artifact(
    copy_id: int, payload: ArtifactEquipIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await artifact_service.set_active(db, user, copy_id, payload.equipped)


@router.post("/artifacts/copies/{copy_id}/gift")
async def gift_artifact(
    copy_id: int, payload: ArtifactGiftIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user),
):
    return await artifact_service.gift(db, user, copy_id, payload.recipient_id)


# --- shared ---------------------------------------------------------------------------


@router.get("/shop/stars-invoices/{payload_token}", response_model=ShopInvoiceStatusOut)
async def shop_invoice_status(payload_token: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await shop_product_service.get_status(db, user, payload_token)
