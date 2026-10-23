"""Trade anti-farming rules.

Every new account starts with coins and free packs, and a trade can hand
coins/cards to anyone — so throwaway accounts could funnel their starter
value into one main account. The rules (all on GameConfig, 0 = off):

- giving anything in a trade (coins or cards, on either side) needs an
  account at least `trade_send_min_account_age_days` old that was active on
  at least `trade_send_min_active_days` distinct days (user_daily_activity);
- a player receives at most `trade_daily_coins_receive_cap` coins through
  trades per local day (sum of today's trade_coins_received rows);
- `trade_coin_tax_pct` of the coin part is burned on accept, paid by the
  side that receives the coins (its own `trade_coin_tax` transaction).

trade_service checks these at create time (early, friendly errors) and again
at accept time under both user row locks — the accept check is the one that
counts, since conditions (config, today's received total) can change while an
offer is pending.
"""
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.models.user_activity import UserDailyActivity


def ensure_trade_shape(
    config: GameConfig, sender_coins: int, receiver_coins: int, offered_cards: int, requested_cards: int,
) -> None:
    """Card-for-card mode: no coins, and (optionally) cards on both sides."""
    if not config.trade_coins_enabled and (sender_coins > 0 or receiver_coins > 0):
        raise ConflictError(
            "Сейчас обмены только «карточка на карточку» — монеты в обмен добавлять нельзя.",
            details={"rule": "trade_coins_disabled"},
        )
    if config.trade_cards_both_sides and (offered_cards == 0 or requested_cards == 0):
        raise ConflictError(
            "В обмене должны быть карточки с обеих сторон: выбери хотя бы одну свою и одну карточку игрока.",
            details={"rule": "trade_cards_both_sides"},
        )


async def active_days(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.count()).select_from(UserDailyActivity).where(UserDailyActivity.user_id == user_id)
    )).scalar_one())


async def give_block_reason(db: AsyncSession, user: User, config: GameConfig) -> Optional[str]:
    """Why `user` may not give coins/cards in a trade yet (None = may)."""
    min_age = config.trade_send_min_account_age_days
    if min_age > 0 and user.created_at is not None:
        left = timedelta(days=min_age) - (datetime.now(timezone.utc) - ensure_aware(user.created_at))
        if left > timedelta(0):
            days_left = max(1, math.ceil(left.total_seconds() / 86400))
            return (
                f"Отдавать монеты и карточки в обменах можно через {min_age} дн. после регистрации. "
                f"Осталось подождать: {days_left} дн."
            )
    min_active = config.trade_send_min_active_days
    if min_active > 0:
        have = await active_days(db, user.id)
        if have < min_active:
            return (
                f"Отдавать монеты и карточки в обменах можно после {min_active} дн. игры "
                f"(дни, когда ты заходил(а) в игру). Сейчас: {have}."
            )
    return None


async def ensure_can_give(db: AsyncSession, user: User, config: GameConfig, *, own: bool) -> None:
    """`own` = `user` is the player making the request (else the trade partner)."""
    reason = await give_block_reason(db, user, config)
    if reason is None:
        return
    if own:
        raise ForbiddenError(reason, details={"rule": "trade_new_account"})
    raise ConflictError(
        "У этого игрока слишком новый аккаунт: он пока не может отдавать монеты и карточки в обменах.",
        details={"rule": "trade_new_account_partner"},
    )


def _today_start_utc() -> datetime:
    return datetime.combine(local_today(), datetime.min.time(), tzinfo=app_timezone()).astimezone(timezone.utc)


async def coins_received_today(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
            CoinTransaction.user_id == user_id,
            CoinTransaction.type == TransactionType.trade_coins_received,
            CoinTransaction.created_at >= _today_start_utc(),
        )
    )).scalar_one())


async def ensure_receive_cap(db: AsyncSession, user: User, incoming: int, config: GameConfig, *, own: bool) -> None:
    cap = config.trade_daily_coins_receive_cap
    if cap <= 0 or incoming <= 0:
        return
    got = await coins_received_today(db, user.id)
    if got + incoming <= cap:
        return
    left = max(0, cap - got)
    details = {"rule": "trade_daily_coins_cap", "cap": cap, "left": left}
    if own:
        raise ConflictError(
            f"Через обмены можно получить не больше {cap} монет в день. "
            f"Сегодня ты уже получил(а) {got}, можно ещё {left}.",
            details=details,
        )
    raise ConflictError(
        f"Этот игрок сегодня уже не может получить столько монет через обмены: "
        f"дневной лимит {cap}, осталось {left}.",
        details=details,
    )


def coin_tax(amount: int, config: GameConfig) -> int:
    """Tax on `amount` traded coins, rounded up so splitting a transfer into
    many small trades doesn't dodge it."""
    pct = config.trade_coin_tax_pct
    if pct <= 0 or amount <= 0:
        return 0
    return min(amount, math.ceil(amount * pct / 100))


async def rules_for(db: AsyncSession, user: User, config: GameConfig) -> dict:
    reason = await give_block_reason(db, user, config)
    return {
        "can_give": reason is None,
        "give_block_reason": reason,
        "min_account_age_days": config.trade_send_min_account_age_days,
        "min_active_days": config.trade_send_min_active_days,
        "daily_coins_receive_cap": config.trade_daily_coins_receive_cap,
        "coins_received_today": await coins_received_today(db, user.id),
        "coin_tax_pct": config.trade_coin_tax_pct,
        "coins_enabled": config.trade_coins_enabled,
        "cards_both_sides": config.trade_cards_both_sides,
    }
