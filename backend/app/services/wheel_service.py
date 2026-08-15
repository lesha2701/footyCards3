import random
import secrets
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, local_today
from app.models.badge import UserBadge
from app.models.enums import CardSource, TransactionType, WheelPrizeType, WheelSpinSource
from app.models.pack import Pack, PackOpening, StarsInvoice
from app.models.user import User
from app.models.wheel import WheelPrize, WheelSpin
from app.schemas.badge import BadgeOut
from app.schemas.pack import OpenedCardOut, PackOpenResult, PackOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut, WheelStatusOut
from app.services.card_creation import create_user_card
from app.services.game_config_service import get_config
from app.services.pack_service import _get_pack_or_404, _duplicate_counts_snapshot, pick_random_player, roll_and_create_cards
from app.services.stars_payment_service import _request_telegram_invoice_link
from app.services.wallet_service import credit_coins, debit_coins, lock_user_for_update


def _next_local_midnight_utc() -> datetime:
    tomorrow = local_today() + timedelta(days=1)
    midnight_local = datetime.combine(tomorrow, time.min, tzinfo=app_timezone())
    return midnight_local.astimezone(timezone.utc)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.wheel_spins_reset_at) if user.wheel_spins_reset_at else None
    if reset_day != today:
        user.wheel_free_spins_used_today = 0
        user.wheel_spins_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _active_prizes(db: AsyncSession) -> list[WheelPrize]:
    # WheelPrize.pack is lazy="joined", but Pack.rarity_probabilities (needed
    # by PackOut, nested in WheelPrizeOut.pack) isn't — without this explicit
    # option, serializing a pack-type prize triggers an async lazy-load
    # outside any awaited context (MissingGreenlet).
    result = await db.execute(
        select(WheelPrize)
        .where(WheelPrize.is_active.is_(True))
        .order_by(WheelPrize.sort_order)
        .options(joinedload(WheelPrize.pack).joinedload(Pack.rarity_probabilities))
    )
    return list(result.unique().scalars().all())


async def get_status(db: AsyncSession, user: User) -> WheelStatusOut:
    config = await get_config(db)
    await _ensure_daily_reset(db, user)
    prizes = await _active_prizes(db)
    return WheelStatusOut(
        free_spins_remaining=max(0, config.wheel_free_spins_per_day - user.wheel_free_spins_used_today),
        free_spins_total=config.wheel_free_spins_per_day,
        next_free_spin_reset_at=_next_local_midnight_utc(),
        spin_cost_coins=config.wheel_spin_cost_coins,
        spin_cost_stars=config.wheel_spin_cost_stars,
        prizes=[WheelPrizeOut.model_validate(p) for p in prizes],
    )


async def _roll_prize(db: AsyncSession) -> WheelPrize:
    prizes = await _active_prizes(db)
    if not prizes:
        raise ConflictError("The wheel has no active prizes configured; contact support")
    return random.choices(prizes, weights=[p.weight for p in prizes], k=1)[0]


async def _grant_prize(db: AsyncSession, user: User, prize: WheelPrize, source: WheelSpinSource) -> WheelSpinResultOut:
    spin = WheelSpin(user_id=user.id, prize_id=prize.id, source=source)

    pack_result: PackOpenResult | None = None
    card_result = None
    badge_result: BadgeOut | None = None
    duplicate_badge_coins: int | None = None

    if prize.prize_type == WheelPrizeType.coins:
        await credit_coins(
            db, user, prize.coins_amount, TransactionType.wheel_spin_reward,
            "Приз колеса фортуны: монеты", related_object_type="wheel_prize", related_object_id=prize.id,
        )
        spin.coins_amount = prize.coins_amount

    elif prize.prize_type == WheelPrizeType.pack:
        pack = await _get_pack_or_404(db, prize.pack_id)
        opening = PackOpening(
            user_id=user.id, pack_id=pack.id, price_paid=0,
            idempotency_key=f"wheel-{user.id}-{datetime.now(timezone.utc).timestamp()}",
            created_at=datetime.now(timezone.utc),
        )
        db.add(opening)
        await db.flush()
        dup_counts = await _duplicate_counts_snapshot(db, user.id)
        opened_items = await roll_and_create_cards(db, user, pack, opening, dup_counts, CardSource.wheel)
        pack_result = PackOpenResult(opening_id=opening.id, pack=PackOut.model_validate(pack), cards=opened_items, new_balance=user.balance)
        spin.pack_opening_id = opening.id

    elif prize.prize_type == WheelPrizeType.card_rarity:
        player = await pick_random_player(db, prize.card_rarity)
        dup_counts = await _duplicate_counts_snapshot(db, user.id)
        user_card = await create_user_card(db, user.id, player.id, CardSource.wheel)
        user_card.player = player
        is_new = dup_counts.get(player.id, 0) == 0
        card_result = OpenedCardOut(card=user_card, is_new=is_new, duplicate_count=dup_counts.get(player.id, 0) + 1)
        spin.user_card_id = user_card.id

    elif prize.prize_type == WheelPrizeType.badge:
        config = await get_config(db)
        existing = await db.execute(
            select(UserBadge).where(UserBadge.user_id == user.id, UserBadge.badge_id == prize.badge_id)
        )
        if existing.scalar_one_or_none() is None:
            db.add(UserBadge(user_id=user.id, badge_id=prize.badge_id))
            badge_result = BadgeOut.model_validate(prize.badge)
            spin.badge_granted = True
        else:
            await credit_coins(
                db, user, config.wheel_duplicate_badge_coins, TransactionType.wheel_spin_reward,
                "Приз колеса фортуны: повтор значка (компенсация)",
                related_object_type="wheel_prize", related_object_id=prize.id,
            )
            duplicate_badge_coins = config.wheel_duplicate_badge_coins
            spin.duplicate_badge_coins = duplicate_badge_coins

    db.add(spin)
    db.add(user)
    await db.flush()

    return WheelSpinResultOut(
        prize=WheelPrizeOut.model_validate(prize),
        new_balance=user.balance,
        pack_result=pack_result,
        card_result=card_result,
        badge_result=badge_result,
        duplicate_badge_coins=duplicate_badge_coins,
    )


async def spin_free(db: AsyncSession, user: User) -> WheelSpinResultOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_daily_reset(db, locked_user)
    if locked_user.wheel_free_spins_used_today >= config.wheel_free_spins_per_day:
        raise ConflictError(
            "No free spins left today",
            details={"next_reset_at": _next_local_midnight_utc().isoformat()},
        )
    locked_user.wheel_free_spins_used_today += 1

    prize = await _roll_prize(db)
    result = await _grant_prize(db, locked_user, prize, WheelSpinSource.free)
    await db.commit()
    return result


async def spin_paid_coins(db: AsyncSession, user: User) -> WheelSpinResultOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await debit_coins(
        db, locked_user, config.wheel_spin_cost_coins, TransactionType.wheel_spin_cost,
        "Платная прокрутка колеса фортуны",
    )

    prize = await _roll_prize(db)
    result = await _grant_prize(db, locked_user, prize, WheelSpinSource.coins)
    await db.commit()
    return result


async def create_spin_invoice(db: AsyncSession, user: User) -> StarsInvoiceCreateOut:
    config = await get_config(db)
    payload_token = secrets.token_urlsafe(16)
    invoice = StarsInvoice(
        user_id=user.id, is_wheel_spin=True, payload_token=payload_token, stars_amount=config.wheel_spin_cost_stars,
    )
    db.add(invoice)
    await db.flush()

    invoice_link = await _request_telegram_invoice_link(
        payload_token, "Прокрутка колеса фортуны", "Одна платная прокрутка колеса фортуны", config.wheel_spin_cost_stars,
    )

    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=config.wheel_spin_cost_stars)
