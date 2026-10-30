from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.database import get_db
from app.models.user import User
from app.schemas.auction import AdminAgentOut, AdminAgentRevokeIn, AdminAuctionRemoveIn, AuctionLotOut
from app.services import agent_license_service, auction_service

router = APIRouter(prefix="/admin/auction", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("/lots", response_model=list[AuctionLotOut])
async def list_lots(status: Optional[str] = None, username: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await auction_service.admin_list(db, status=status, username=username)


@router.get("/lots/{lot_id}", response_model=AuctionLotOut)
async def get_lot(lot_id: int, db: AsyncSession = Depends(get_db)):
    return await auction_service.admin_get(db, lot_id)


@router.post("/lots/{lot_id}/remove", response_model=AuctionLotOut)
async def remove_lot(
    lot_id: int, payload: AdminAuctionRemoveIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    return await auction_service.admin_remove(
        db, admin, lot_id, payload.reason, ip_address=request.client.host if request.client else None,
    )


@router.get("/agents", response_model=list[AdminAgentOut])
async def list_agents(only_active: bool = False, db: AsyncSession = Depends(get_db)):
    return await agent_license_service.admin_list(db, only_active=only_active)


@router.post("/agents/{user_id}/revoke", response_model=AdminAgentOut)
async def revoke_agent(
    user_id: int, payload: AdminAgentRevokeIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    """Ends a «Агентская лицензия» at once — e.g. after a Stars refund made
    outside the app. Running lots stay until they end."""
    return await agent_license_service.admin_revoke(
        db, admin, user_id, payload.reason, ip_address=request.client.host if request.client else None,
    )
