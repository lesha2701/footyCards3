"""«Агентская лицензия»: the right to put lots on «Трансферный рынок».

Bought for Telegram Stars as the shop product "agent_license"
(shop_product_service → validate_stars at pre-checkout, deliver_stars under
the invoice's row lock; the invoice's completed_at makes delivery once-only).
Each purchase adds GameConfig.agent_license_days to max(now, expires_at), so
buying early extends. Who may buy: an account at least
agent_license_min_account_age_days old that is also a «Проверенный аккаунт»
(card_value_service.verified_block_reason) — a license is for established
players, not fresh multi-accounts. A ban or trade ban doesn't delete the
license but auction_service refuses listing anyway. An admin can revoke it
(e.g. after a Stars refund made outside the app); delivered purchases are
never refunded in-app (stars_receipt_service).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.auction import AgentLicense
from app.models.game_config import GameConfig
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.auction import AdminAgentOut, AgentLicenseOut
from app.services.admin_log_service import log_action
from app.services.game_config_service import get_config
from app.services.wallet_service import lock_user_for_update

PRODUCT = "agent_license"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_active(lic: Optional[AgentLicense], now: Optional[datetime] = None) -> bool:
    return lic is not None and lic.revoked_at is None and ensure_aware(lic.expires_at) > (now or _now())


async def get_license(db: AsyncSession, user_id: int) -> Optional[AgentLicense]:
    return await db.get(AgentLicense, user_id)


async def has_active(db: AsyncSession, user_id: int) -> bool:
    return is_active(await get_license(db, user_id))


async def buy_block_reason(db: AsyncSession, user: User, config: GameConfig) -> Optional[str]:
    """Why `user` can't buy (or extend) the license now; None = they can."""
    if not config.agent_license_enabled:
        return "Агентские лицензии сейчас не продаются"
    if user.is_banned:
        return "Аккаунт заблокирован"
    if user.is_trade_banned:
        return "Тебе временно запрещено торговать"
    days = max(0, config.agent_license_min_account_age_days)
    if days and user.created_at is not None and _now() - ensure_aware(user.created_at) < timedelta(days=days):
        left = timedelta(days=days) - (_now() - ensure_aware(user.created_at))
        return f"Лицензия доступна аккаунтам старше {days} дн. — осталось {max(1, left.days + (1 if left.seconds else 0))} дн."
    if config.agent_license_requires_verified:
        from app.services.card_value_service import verified_block_reason

        reason = await verified_block_reason(db, user, config)
        if reason:
            return reason
    return None


async def status(db: AsyncSession, user: User, config: Optional[GameConfig] = None) -> AgentLicenseOut:
    config = config or await get_config(db)
    lic = await get_license(db, user.id)
    active = is_active(lic)
    return AgentLicenseOut(
        enabled=config.agent_license_enabled,
        active=active,
        expires_at=ensure_aware(lic.expires_at) if lic is not None and lic.revoked_at is None else None,
        revoked=lic is not None and lic.revoked_at is not None and not active,
        stars=config.agent_license_stars,
        days=config.agent_license_days,
        min_account_age_days=config.agent_license_min_account_age_days,
        requires_verified=config.agent_license_requires_verified,
        buy_block_reason=await buy_block_reason(db, user, config),
    )


async def stars_order(db: AsyncSession, user: User) -> tuple:
    """(product, stars, title, description) for shop_product_service.create_invoice."""
    config = await get_config(db)
    reason = await buy_block_reason(db, user, config)
    if reason:
        raise ConflictError(reason)
    if config.agent_license_stars <= 0:
        raise ConflictError("Агентские лицензии сейчас не продаются")
    extend = " (продление)" if await has_active(db, user.id) else ""
    return (
        PRODUCT,
        config.agent_license_stars,
        f"Агентская лицензия{extend}",
        f"Право выставлять карточки на «Трансферный рынок» на {config.agent_license_days} дн. "
        "Ставить и покупать на рынке можно и без лицензии.",
    )


async def validate_stars(db: AsyncSession, user_id: int, stars_amount: int) -> tuple[bool, str]:
    """Pre-checkout: still allowed and the price unchanged (delivery never refuses)."""
    config = await get_config(db)
    user = await db.get(User, user_id)
    if user is None:
        return False, "Игрок не найден"
    reason = await buy_block_reason(db, user, config)
    if reason:
        return False, reason
    if config.agent_license_stars <= 0 or config.agent_license_stars != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice: StarsInvoice) -> dict:
    """Already paid: adds agent_license_days. The user row lock serializes two
    invoices of the same player delivered at once (the row insert would race
    otherwise). The caller holds the invoice lock and commits."""
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    now = _now()
    lic = (
        await db.execute(
            select(AgentLicense).where(AgentLicense.user_id == locked.id)
            .with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    days = timedelta(days=max(1, config.agent_license_days))
    if lic is None:
        lic = AgentLicense(user_id=locked.id, expires_at=now + days, first_bought_at=now, last_bought_at=now,
                           purchases=0, stars_total=0)
        db.add(lic)
    else:
        base = ensure_aware(lic.expires_at) if is_active(lic, now) else now
        lic.expires_at = base + days
        lic.revoked_at = None
        lic.revoke_reason = None
        lic.last_bought_at = now
    lic.purchases = (lic.purchases or 0) + 1
    lic.stars_total = (lic.stars_total or 0) + invoice.stars_amount
    return {"kind": PRODUCT, "expires_at": lic.expires_at.isoformat()}


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

async def admin_list(db: AsyncSession, only_active: bool = False, limit: int = 300) -> list[AdminAgentOut]:
    rows = (
        await db.execute(
            select(AgentLicense, User).join(User, User.id == AgentLicense.user_id)
            .order_by(AgentLicense.expires_at.desc()).limit(limit)
        )
    ).all()
    out = [_agent_out(lic, user) for lic, user in rows]
    return [a for a in out if a.active] if only_active else out


def _agent_out(lic: AgentLicense, user: User) -> AdminAgentOut:
    return AdminAgentOut(
        user_id=user.id, username=user.username, name=user.full_display_name(), active=is_active(lic),
        expires_at=ensure_aware(lic.expires_at), first_bought_at=ensure_aware(lic.first_bought_at),
        purchases=lic.purchases, stars_total=lic.stars_total,
        revoked_at=ensure_aware(lic.revoked_at) if lic.revoked_at else None, revoke_reason=lic.revoke_reason,
        is_banned=user.is_banned, is_trade_banned=user.is_trade_banned,
    )


async def admin_revoke(
    db: AsyncSession, admin: User, user_id: int, reason: str, ip_address: Optional[str] = None,
) -> AdminAgentOut:
    """Ends a license at once (lots already on the market run to their end)."""
    lic = (
        await db.execute(
            select(AgentLicense).where(AgentLicense.user_id == user_id)
            .with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if lic is None:
        raise NotFoundError("У игрока нет лицензии")
    if lic.revoked_at is not None:
        raise ConflictError("Лицензия уже отозвана")
    old = {"expires_at": ensure_aware(lic.expires_at).isoformat()}
    lic.revoked_at = _now()
    lic.revoke_reason = reason
    await log_action(
        db, admin.id, "agent_license_revoke", "agent_license", user_id,
        old_value=old, new_value={"revoked": True}, ip_address=ip_address, extra=reason,
    )
    await db.commit()
    return _agent_out(lic, await db.get(User, user_id))
