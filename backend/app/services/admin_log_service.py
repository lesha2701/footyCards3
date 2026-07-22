from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_action import AdminAction


async def log_action(
    db: AsyncSession,
    admin_id: int,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    old_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    ip_address: Optional[str] = None,
    extra: Optional[str] = None,
) -> AdminAction:
    entry = AdminAction(
        admin_id=admin_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        extra=extra,
    )
    db.add(entry)
    return entry
