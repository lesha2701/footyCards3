from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.dependencies import _get_or_create_user
from app.core.exceptions import ConflictError, RateLimitedError
from app.core.security import TelegramUser
from app.core.timeutil import ensure_aware
from app.models.enums import CardSource
from app.models.pack import Pack, PackOpening
from app.models.user import User
from app.schemas.pack import PackOpenResult, PackOut
from app.services.game_config_service import get_config
from app.services.wallet_service import lock_user_for_update


def _is_available(user: User) -> bool:
    if user.chat_pack_available_at is None:
        return True
    return ensure_aware(user.chat_pack_available_at) <= datetime.now(timezone.utc)


async def _grant_chat_pack(db: AsyncSession, user: User, slug: str) -> Optional[PackOpenResult]:
    # Deferred: avoids a circular import with pack_service (mirrors
    # free_pack_service._grant_free_pack).
    from app.services.pack_service import _duplicate_counts_snapshot, roll_and_create_cards, track_pack_opened_tasks

    result = await db.execute(
        select(Pack).where(Pack.slug == slug).options(joinedload(Pack.rarity_probabilities))
    )
    pack = result.unique().scalar_one_or_none()
    if not pack:
        return None

    opening = PackOpening(
        user_id=user.id, pack_id=pack.id, price_paid=0,
        idempotency_key=f"chat-pack-{user.id}-{datetime.now(timezone.utc).timestamp()}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(opening)
    await db.flush()

    dup_counts = await _duplicate_counts_snapshot(db, user.id)
    opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, CardSource.chat_pack)
    await track_pack_opened_tasks(db, user, dup_counts)

    return PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=opened_items, new_balance=user.balance)


async def claim_chat_pack_for_telegram_user(
    db: AsyncSession,
    telegram_user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
) -> PackOpenResult:
    """Grants the "вкарта" group-chat promo pack for a Telegram user, on its
    own cooldown (`User.chat_pack_available_at` / `config.chat_pack_interval_hours`)
    independent of the in-app free pack. Called by the bot via the internal
    API — see routers/internal.py.

    Anyone can trigger this from a group chat, registered or not — an
    unregistered user is signed up on the spot (same `_get_or_create_user`
    path as opening the Mini App for the first time, including the starting
    coin bonus) instead of being turned away, since the whole point of chat
    mode is picking up new players who haven't opened the app yet."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        tg_user = TelegramUser(id=telegram_user_id, username=username, first_name=first_name, last_name=last_name)
        user = await _get_or_create_user(db, tg_user)

    if user.is_banned:
        raise ConflictError("User is banned")

    if not _is_available(user):
        raise RateLimitedError(
            "Chat pack not available yet", details={"available_at": user.chat_pack_available_at.isoformat()}
        )

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    if not _is_available(locked_user):
        raise RateLimitedError(
            "Chat pack not available yet", details={"available_at": locked_user.chat_pack_available_at.isoformat()}
        )

    grant_result = await _grant_chat_pack(db, locked_user, config.free_pack_pack_slug)
    if grant_result is None:
        raise ConflictError("Chat pack is not configured correctly; contact support")

    next_available_at = datetime.now(timezone.utc) + timedelta(hours=config.chat_pack_interval_hours)
    locked_user.chat_pack_available_at = next_available_at
    db.add(locked_user)
    await db.commit()
    await db.refresh(locked_user)

    grant_result.new_balance = locked_user.balance
    return grant_result
