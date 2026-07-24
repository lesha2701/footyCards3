from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import TelegramAuthError, TelegramUser, decode_admin_token, validate_init_data
from app.database import get_db
from app.models.enums import TransactionType
from app.models.user import User
from app.services.wallet_service import credit_coins

settings = get_settings()


async def _get_or_create_user(
    db: AsyncSession, tg_user: TelegramUser, referral_code: Optional[str] = None
) -> User:
    result = await db.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()
    is_admin_now = tg_user.id in settings.admin_ids

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            avatar_url=tg_user.photo_url,
            balance=0,
            is_admin=is_admin_now,
        )
        db.add(user)
        await db.flush()
        await credit_coins(
            db,
            user,
            settings.starting_balance,
            TransactionType.starting_balance,
            "Стартовый бонус при регистрации",
        )
        user.received_starting_bonus = True

        if referral_code:
            try:
                ref_telegram_id = int(referral_code)
            except ValueError:
                ref_telegram_id = None
            if ref_telegram_id is not None and ref_telegram_id != tg_user.id:
                referrer_result = await db.execute(select(User).where(User.telegram_id == ref_telegram_id))
                referrer = referrer_result.scalar_one_or_none()
                if referrer is not None:
                    # Only record the relationship here — referral_count is
                    # credited later, on the referred user's first genuine
                    # paid purchase (see pack_service.open_pack). Crediting
                    # it immediately on registration would let anyone farm
                    # referral rewards with disposable, never-used accounts
                    # via this client-supplied header alone.
                    user.referred_by_id = referrer.id

        await db.commit()
        await db.refresh(user)
        return user

    changed = False
    if user.username != tg_user.username:
        user.username = tg_user.username
        changed = True
    if user.first_name != tg_user.first_name:
        user.first_name = tg_user.first_name
        changed = True
    if user.last_name != tg_user.last_name:
        user.last_name = tg_user.last_name
        changed = True
    if tg_user.photo_url and user.avatar_url != tg_user.photo_url:
        user.avatar_url = tg_user.photo_url
        changed = True
    if user.is_admin != is_admin_now:
        user.is_admin = is_admin_now
        changed = True
    user.last_seen_at = datetime.now(timezone.utc)
    if changed:
        await db.commit()
        await db.refresh(user)
    else:
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_init_data: Optional[str] = Header(default=None, alias="X-Telegram-Init-Data"),
    x_dev_mode: Optional[str] = Header(default=None, alias="X-Dev-Mode"),
    x_referral_code: Optional[str] = Header(default=None, alias="X-Referral-Code"),
) -> User:
    if x_telegram_init_data:
        try:
            tg_user = validate_init_data(x_telegram_init_data, settings.telegram_bot_token)
        except TelegramAuthError as exc:
            raise UnauthorizedError(f"Telegram auth failed: {exc}") from exc
    elif settings.dev_mode and x_dev_mode == "true":
        tg_user = TelegramUser(
            id=settings.dev_user_telegram_id,
            username="dev_user",
            first_name="Dev",
            last_name="User",
            photo_url=None,
        )
    else:
        raise UnauthorizedError("Missing Telegram init data")

    user = await _get_or_create_user(db, tg_user, referral_code=x_referral_code)
    if user.is_banned:
        raise ForbiddenError("This account has been banned")
    return user


async def get_current_admin_via_telegram(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ForbiddenError("Admin access required")
    return user


async def get_current_admin(
    db: AsyncSession = Depends(get_db),
    authorization: Optional[str] = Header(default=None),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing admin bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_admin_token(token)
    except TelegramAuthError as exc:
        raise UnauthorizedError(f"Invalid admin token: {exc}") from exc

    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if user is None:
        raise UnauthorizedError("Admin user not found")
    if user.telegram_id not in settings.admin_ids or not user.is_admin:
        raise ForbiddenError("Admin access required")
    if user.is_banned:
        raise ForbiddenError("This account has been banned")
    return user
