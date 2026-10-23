"""«Стартовое предложение»: a one-time Stars bundle (coins + a pack + an
exclusive cosmetic, all GameConfig.starter_offer_*) for new players during
their first `starter_offer_hours` hours. With `starter_offer_for_all` on,
every player who hasn't bought it gets it too: the window then starts at
the later of registration and `starter_offer_all_since` (the moment the
switch went on), and a player who saw it before that sees it full-screen
once more. It is shown full-screen once
(`users.starter_offer_seen_at`), then stays as a banner with a countdown
until it is bought or runs out. One purchase per player
(starter_offer_purchases.user_id is unique; pre-checkout refuses a second)."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import ensure_aware
from app.models.enums import CardSource, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import StarterOfferPurchase
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.monetization import StarterOfferOut
from app.services import reward_bundle_service
from app.services.game_config_service import get_config
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update


def _bundle(config: GameConfig) -> Bundle:
    return Bundle(
        coins=config.starter_offer_coins, pack_id=config.starter_offer_pack_id,
        cosmetic_id=config.starter_offer_cosmetic_id,
    )


def _all_since(config: GameConfig) -> Optional[datetime]:
    if config.starter_offer_for_all and config.starter_offer_all_since is not None:
        return ensure_aware(config.starter_offer_all_since)
    return None


def expires_at(user: User, config: GameConfig) -> datetime:
    start = ensure_aware(user.created_at)
    since = _all_since(config)
    if since is not None and since > start:
        start = since
    return start + timedelta(hours=config.starter_offer_hours)


def _seen(user: User, config: GameConfig) -> bool:
    if user.starter_offer_seen_at is None:
        return False
    since = _all_since(config)
    return since is None or ensure_aware(user.starter_offer_seen_at) >= since


async def _purchased(db: AsyncSession, user_id: int) -> bool:
    return (await db.execute(
        select(StarterOfferPurchase.id).where(StarterOfferPurchase.user_id == user_id)
    )).first() is not None


async def _available(db: AsyncSession, user: User, config: GameConfig, now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return config.starter_offer_enabled and now < expires_at(user, config) and not await _purchased(db, user.id)


async def get_status(db: AsyncSession, user: User) -> StarterOfferOut:
    config = await get_config(db)
    purchased = await _purchased(db, user.id)
    if not await _available(db, user, config):
        return StarterOfferOut(available=False, purchased=purchased)
    return StarterOfferOut(
        available=True, stars_price=config.starter_offer_stars,
        contents=await reward_bundle_service.describe(db, _bundle(config)),
        expires_at=expires_at(user, config), seen=_seen(user, config),
    )


async def mark_seen(db: AsyncSession, user: User) -> StarterOfferOut:
    if not _seen(user, await get_config(db)):
        user.starter_offer_seen_at = datetime.now(timezone.utc)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return await get_status(db, user)


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    if not await _available(db, user, config):
        raise ConflictError("Стартовое предложение больше недоступно")
    contents = await reward_bundle_service.describe(db, _bundle(config))
    parts = [f"{contents.coins} монет"] if contents.coins else []
    if contents.pack_name:
        parts.append(f"пак «{contents.pack_name}»")
    if contents.cosmetic:
        parts.append(f"эксклюзивная рамка «{contents.cosmetic.name}»")
    return (
        "starter_offer", config.starter_offer_stars, "Стартовое предложение",
        "Один раз на аккаунт: " + (", ".join(parts) or "набор новичка") + ".",
    )


async def validate_stars(db: AsyncSession, user_id: int, stars_amount: int) -> tuple[bool, str]:
    config = await get_config(db)
    user = await db.get(User, user_id)
    if user is None or not await _available(db, user, config):
        return False, "Стартовое предложение больше недоступно"
    if config.starter_offer_stars != stars_amount:
        return False, "Цена изменилась — открой покупку заново"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, invoice: StarsInvoice) -> dict:
    """Already paid: never refuses (pre-checkout is what keeps it one per
    player). The caller commits."""
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    try:
        async with db.begin_nested():
            db.add(StarterOfferPurchase(user_id=locked.id, stars_amount=invoice.stars_amount))
            await db.flush()
    except IntegrityError:
        pass  # two paid invoices raced past pre-checkout — both were paid, both are delivered
    await reward_bundle_service.grant(
        db, locked, _bundle(config), tx_type=TransactionType.starter_offer_reward,
        description="Стартовое предложение", card_source=CardSource.stars_purchase,
        idempotency_prefix=f"starter-{invoice.payload_token}", cosmetic_source="starter_offer",
        related_object_type="stars_invoice", related_object_id=invoice.id,
    )
    return {"kind": "starter_offer"}
