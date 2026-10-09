from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.models.card_skill import CardSkillLedger
from app.models.user import User
from app.schemas.card_skill import (
    AdminSkillUpdate,
    AdminTokenGrantRequest,
    AdminUserTokensOut,
    SkillCatalogOut,
    SkillLedgerEntryOut,
)
from app.services import card_skill_service
from app.services.admin_log_service import log_action
from app.services.card_skill_catalog import SKILL_DEFINITIONS
from app.services.wallet_service import lock_user_for_update

# Economy (bonus per level, event cap, probability bounds, every price, the
# global on/off switch, tournament token rewards) is edited through the
# existing PUT /admin/games/config — GameConfig stays the single source of
# truth. This router owns only the per-skill catalog state, token grants and
# the operation history.
router = APIRouter(prefix="/admin/card-skills", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("", response_model=SkillCatalogOut)
async def admin_catalog(db: AsyncSession = Depends(get_db)):
    return await card_skill_service.get_catalog(db)


@router.patch("/{code}", response_model=SkillCatalogOut)
async def update_skill(
    code: str, payload: AdminSkillUpdate, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    definition = SKILL_DEFINITIONS.get(code)
    if definition is None:
        raise NotFoundError("Unknown skill")
    rows = await card_skill_service.ensure_catalog(db)
    row = rows[code]
    old_value = {"is_enabled": row.is_enabled, "allowed_positions": row.allowed_positions, "sort_order": row.sort_order}

    if payload.is_enabled is not None:
        if payload.is_enabled and not definition.engine_supported:
            raise ConflictError(
                definition.unavailable_reason or "Навык не поддерживается движком",
                details={"reason": "skill_unsupported"},
            )
        row.is_enabled = payload.is_enabled
    if payload.reset_positions:
        row.allowed_positions = None
    elif payload.allowed_positions is not None:
        requested = list(dict.fromkeys(payload.allowed_positions))
        outside = [p.value for p in requested if p not in definition.positions]
        if outside:
            raise ConflictError(
                "Эти позиции не допускаются серверными правилами навыка",
                details={"reason": "positions_outside_catalog", "positions": outside},
            )
        if not requested:
            raise ConflictError("Нужна хотя бы одна позиция", details={"reason": "empty_positions"})
        row.allowed_positions = [p.value for p in requested]
    if payload.sort_order is not None:
        row.sort_order = payload.sort_order
    db.add(row)
    await log_action(
        db, admin.id, "update_card_skill", "card_skill", None, old_value=old_value,
        new_value={"code": code, **payload.model_dump(mode="json", exclude_unset=True)}, ip_address=_ip(request),
        extra=code,
    )
    await db.commit()
    return await card_skill_service.get_catalog(db)


@router.get("/tokens/{user_id}", response_model=AdminUserTokensOut)
async def user_tokens(user_id: int, db: AsyncSession = Depends(get_db)):
    if await db.get(User, user_id) is None:
        raise NotFoundError("User not found")
    balances = await card_skill_service.get_token_balances(db, user_id)
    return AdminUserTokensOut(user_id=user_id, tokens=card_skill_service.balances_out(balances))


@router.post("/tokens/grant", response_model=AdminUserTokensOut)
async def grant_tokens(
    payload: AdminTokenGrantRequest, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    if payload.quantity == 0:
        raise ConflictError("Количество не может быть нулевым", details={"reason": "zero_quantity"})
    if await db.get(User, payload.user_id) is None:
        raise NotFoundError("User not found")
    card_skill_service.validate_grantable_skill(payload.skill_code)

    target = await lock_user_for_update(db, payload.user_id)
    entry = await card_skill_service.grant_tokens(
        db, target, payload.skill_code, payload.quantity,
        "grant_admin" if payload.quantity > 0 else "revoke_admin",
        admin_id=admin.id, reason=payload.reason, idempotency_key=payload.idempotency_key,
        related_object_type="admin_action",
    )
    if entry is not None:
        await log_action(
            db, admin.id, "grant_skill_tokens" if payload.quantity > 0 else "revoke_skill_tokens", "user",
            payload.user_id, new_value=payload.model_dump(mode="json"), ip_address=_ip(request), extra=payload.reason,
        )
    try:
        await db.commit()
    except IntegrityError:
        # Same idempotency key raced in from a double-submit: the other
        # request's grant is the one that counts.
        await db.rollback()
    balances = await card_skill_service.get_token_balances(db, payload.user_id)
    return AdminUserTokensOut(user_id=payload.user_id, tokens=card_skill_service.balances_out(balances))


@router.get("/ledger", response_model=list[SkillLedgerEntryOut])
async def ledger(
    user_id: Optional[int] = None, skill_code: Optional[str] = None, kind: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500), db: AsyncSession = Depends(get_db),
):
    query = select(CardSkillLedger)
    if user_id is not None:
        query = query.where(CardSkillLedger.user_id == user_id)
    if skill_code:
        query = query.where(CardSkillLedger.skill_code == skill_code)
    if kind:
        query = query.where(CardSkillLedger.kind == kind)
    result = await db.execute(query.order_by(CardSkillLedger.created_at.desc(), CardSkillLedger.id.desc()).limit(limit))
    return result.scalars().all()
