from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.card_upgrade import CardUpgradeRule
from app.models.user import User
from app.schemas.card_upgrade import CardUpgradeRuleOut, CardUpgradeRuleUpdate
from app.services.admin_log_service import log_action
from app.services.card_upgrade_service import list_rules

router = APIRouter(prefix="/admin/card-upgrades", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.get("", response_model=list[CardUpgradeRuleOut])
async def list_all_rules(db: AsyncSession = Depends(get_db)):
    return await list_rules(db)


@router.put("/{rule_id}", response_model=CardUpgradeRuleOut)
async def update_rule(
    rule_id: int,
    payload: CardUpgradeRuleUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    rule = await db.get(CardUpgradeRule, rule_id)
    if rule is None:
        raise NotFoundError("Upgrade rule not found")

    old_value = CardUpgradeRuleOut.model_validate(rule).model_dump(mode="json")
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(rule, key, value)
    db.add(rule)

    await log_action(
        db, admin.id, "update_card_upgrade_rule", "card_upgrade_rule", rule_id,
        old_value=old_value, new_value=updates,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(rule)
    return rule
