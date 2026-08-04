from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.coin_package import CoinPackage
from app.models.user import User
from app.schemas.stars import CoinPackageOut
from app.services.admin_log_service import log_action

router = APIRouter(prefix="/admin/coin-packages", tags=["admin"], dependencies=[Depends(get_current_admin)])


class CoinPackageCreate(BaseModel):
    stars_price: int = Field(ge=1)
    coins_amount: int = Field(ge=1)
    is_active: bool = True
    sort_order: int = 0


class CoinPackageUpdate(BaseModel):
    stars_price: int | None = Field(default=None, ge=1)
    coins_amount: int | None = Field(default=None, ge=1)
    is_active: bool | None = None
    sort_order: int | None = None


async def _get_package_or_404(db: AsyncSession, package_id: int) -> CoinPackage:
    package = await db.get(CoinPackage, package_id)
    if package is None:
        raise NotFoundError("Coin package not found")
    return package


@router.get("", response_model=list[CoinPackageOut])
async def list_all_coin_packages(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CoinPackage).order_by(CoinPackage.sort_order))
    return result.scalars().all()


@router.post("", response_model=CoinPackageOut)
async def create_coin_package(payload: CoinPackageCreate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    package = CoinPackage(**payload.model_dump())
    db.add(package)
    await db.flush()
    await log_action(
        db, admin.id, "create_coin_package", "coin_package", package.id,
        new_value=payload.model_dump(mode="json"), ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(package)
    return package


@router.put("/{package_id}", response_model=CoinPackageOut)
async def update_coin_package(package_id: int, payload: CoinPackageUpdate, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    package = await _get_package_or_404(db, package_id)
    old_value = CoinPackageOut.model_validate(package).model_dump(mode="json")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(package, key, value)
    db.add(package)

    await log_action(
        db, admin.id, "update_coin_package", "coin_package", package_id,
        old_value=old_value, new_value=updates, ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(package)
    return package


@router.delete("/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_coin_package(package_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin)):
    package = await _get_package_or_404(db, package_id)
    await log_action(
        db, admin.id, "delete_coin_package", "coin_package", package_id,
        old_value=CoinPackageOut.model_validate(package).model_dump(mode="json"),
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(package)
    await db.commit()
