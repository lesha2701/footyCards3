from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.diamond_upgrade import DiamondUpgradeTier
from app.models.user import User
from app.schemas.diamond_upgrade import DiamondUpgradeTierCreate, DiamondUpgradeTierOut, DiamondUpgradeTierUpdate
from app.services.admin_log_service import log_action
from app.services.diamond_upgrade_service import list_tiers

router = APIRouter(prefix="/admin/diamond-upgrade-tiers", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[DiamondUpgradeTierOut])
async def list_all_tiers(db: AsyncSession = Depends(get_db)):
    return await list_tiers(db)


@router.post("", response_model=DiamondUpgradeTierOut)
async def create_tier(
    payload: DiamondUpgradeTierCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    tier = DiamondUpgradeTier(**payload.model_dump())
    db.add(tier)
    await db.flush()

    await log_action(
        db, admin.id, "create_diamond_upgrade_tier", "diamond_upgrade_tier", tier.id,
        old_value=None, new_value=payload.model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tier)
    return tier


@router.put("/{tier_id}", response_model=DiamondUpgradeTierOut)
async def update_tier(
    tier_id: int,
    payload: DiamondUpgradeTierUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    tier = await db.get(DiamondUpgradeTier, tier_id)
    if tier is None:
        raise NotFoundError("Diamond upgrade tier not found")

    old_value = DiamondUpgradeTierOut.model_validate(tier).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tier, key, value)
    db.add(tier)

    await log_action(
        db, admin.id, "update_diamond_upgrade_tier", "diamond_upgrade_tier", tier_id,
        old_value=old_value, new_value=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tier)
    return tier


@router.delete("/{tier_id}")
async def delete_tier(
    tier_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    tier = await db.get(DiamondUpgradeTier, tier_id)
    if tier is None:
        raise NotFoundError("Diamond upgrade tier not found")

    old_value = DiamondUpgradeTierOut.model_validate(tier).model_dump(mode="json")
    await db.delete(tier)

    await log_action(
        db, admin.id, "delete_diamond_upgrade_tier", "diamond_upgrade_tier", tier_id,
        old_value=old_value, new_value=None,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    return {"ok": True}
