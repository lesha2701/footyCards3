"""Anti-farming rules for coin stakes in open chat challenges (Тактико,
Стратего, Пенальти).

A stake is a coin transfer in disguise: a main account challenges its own
alt for a big stake, the alt accepts and loses on purpose, and the pot lands
on the main. The rules (all on GameConfig, 0 = off):

- `stake_max_coins` — the largest stake one side may put in;
- both players must pass the trade give rules (account age + active days,
  trade_guard_service) — a new account can't stake;
- `stake_pair_daily_limit` — staked matches the same two players may start
  per local day, across all three games;
- `stake_daily_profit_cap` — a player can't join a new staked match once
  their net stake result today (wins + refunds − stakes put in), plus this
  stake, would exceed the cap.

create_open_challenge checks the creator early; accept_open_challenge
checks everything again under both user locks, which is the check that
counts (the config or today's results may change while a challenge waits).
"""
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, local_today
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.penalty import PenaltyMatch
from app.models.stratego import StrategoMatch
from app.models.tactico import TacticoMatch
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import trade_guard_service

STAKE_TX_TYPES = (
    TransactionType.tactico_stake_lock, TransactionType.tactico_stake_win, TransactionType.tactico_stake_refund,
    TransactionType.penalty_stake_lock, TransactionType.penalty_stake_win, TransactionType.penalty_stake_refund,
    TransactionType.stratego_stake_lock, TransactionType.stratego_stake_win, TransactionType.stratego_stake_refund,
)
STAKED_MATCH_MODELS = (TacticoMatch, PenaltyMatch, StrategoMatch)


def _today_start_utc() -> datetime:
    return datetime.combine(local_today(), datetime.min.time(), tzinfo=app_timezone()).astimezone(timezone.utc)


async def _ensure_can_stake(db: AsyncSession, user: User, config: GameConfig, *, own: bool) -> None:
    """Same account age / activity bar as giving in a trade."""
    reason = await trade_guard_service.give_block_reason(db, user, config)
    if reason is None:
        return
    if own:
        raise ConflictError(
            "Играть на ставку можно, когда аккаунту исполнится "
            f"{config.trade_send_min_account_age_days} дн. и ты будешь заходить в игру хотя бы "
            f"{config.trade_send_min_active_days} разных дн. Пока сыграй без ставки.",
            details={"rule": "stake_new_account"},
        )
    raise ConflictError(
        "У автора вызова слишком новый аккаунт для игры на ставку.", details={"rule": "stake_new_account_partner"},
    )


def ensure_stake_size(config: GameConfig, stake: int) -> None:
    if stake <= 0:
        return
    if config.stake_max_coins <= 0:
        raise ConflictError("Ставки в вызовах сейчас отключены — играй без ставки.", details={"rule": "stakes_disabled"})
    if stake > config.stake_max_coins:
        raise ConflictError(
            f"Ставка не может быть больше {config.stake_max_coins} монет.",
            details={"rule": "stake_max", "max": config.stake_max_coins},
        )


async def stake_profit_today(db: AsyncSession, user_id: int) -> int:
    return int((await db.execute(
        select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
            CoinTransaction.user_id == user_id,
            CoinTransaction.type.in_(STAKE_TX_TYPES),
            CoinTransaction.created_at >= _today_start_utc(),
        )
    )).scalar_one())


async def _ensure_profit_cap(db: AsyncSession, user: User, stake: int, config: GameConfig, *, own: bool) -> None:
    cap = config.stake_daily_profit_cap
    if cap <= 0:
        return
    profit = await stake_profit_today(db, user.id)
    if profit + stake <= cap:
        return
    details = {"rule": "stake_daily_profit_cap", "cap": cap}
    if own:
        raise ConflictError(
            f"Сегодня ты уже выиграл(а) на ставках {max(0, profit)} монет — это дневной лимит ({cap}). "
            "Играй без ставки или возвращайся завтра.",
            details=details,
        )
    raise ConflictError("Соперник сегодня достиг дневного лимита выигрышей на ставках.", details=details)


async def staked_matches_today(db: AsyncSession, a_id: int, b_id: int) -> int:
    since = _today_start_utc()
    total = 0
    for model in STAKED_MATCH_MODELS:
        pair = or_(
            and_(model.user_id == a_id, model.opponent_user_id == b_id),
            and_(model.user_id == b_id, model.opponent_user_id == a_id),
        )
        total += int((await db.execute(
            select(func.count()).select_from(model).where(pair, model.stake_coins > 0, model.created_at >= since)
        )).scalar_one())
    return total


async def ensure_can_create(db: AsyncSession, creator: User, stake: int, config: GameConfig) -> None:
    if stake <= 0:
        return
    ensure_stake_size(config, stake)
    await _ensure_can_stake(db, creator, config, own=True)
    await _ensure_profit_cap(db, creator, stake, config, own=True)


async def ensure_can_accept(db: AsyncSession, creator: User, acceptor: User, stake: int, config: GameConfig) -> None:
    """Call with both users locked, before any stake is debited."""
    if stake <= 0:
        return
    ensure_stake_size(config, stake)
    await _ensure_can_stake(db, acceptor, config, own=True)
    await _ensure_can_stake(db, creator, config, own=False)
    limit = config.stake_pair_daily_limit
    if limit > 0 and await staked_matches_today(db, creator.id, acceptor.id) >= limit:
        raise ConflictError(
            f"С этим игроком сегодня уже сыграно матчей на ставку: {limit}. Сыграйте без ставки или завтра.",
            details={"rule": "stake_pair_daily_limit", "limit": limit},
        )
    await _ensure_profit_cap(db, acceptor, stake, config, own=True)
    await _ensure_profit_cap(db, creator, stake, config, own=False)
