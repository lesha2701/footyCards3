"""«21: Добавленное время» — DB, entries/limits, Stars purchase and rewards.
The rules themselves are in blackjack_engine.py.

Entries: config.blackjack_free_per_day free hands a day; beyond that a hand
costs one banked entry — either a paid one (bought for Telegram Stars via
the regular StarsInvoice flow, at most config.blackjack_paid_daily_limit
purchases a local day) or a replay one (granted by a draw). Consumption
order: free → replay → paid.

Rewards go through wheel_service: a «Хет-трик» rolls the jackpot pool, a
plain win the golden pool (falling back to the next pool down if an admin
left one empty), a loss pays config.blackjack_consolation_coins.
"""
import secrets
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import app_timezone, local_today
from app.models.blackjack import BlackjackMatch
from app.models.enums import TransactionType, WheelPrizePool, WheelSpinSource
from app.models.game_config import GameConfig
from app.models.pack import Pack, StarsInvoice
from app.models.user import User
from app.models.wheel import WheelPrize, WheelSpin
from app.schemas.blackjack import BlackjackActionOut, BlackjackCardOut, BlackjackMatchOut, BlackjackStatusOut
from app.schemas.stars import StarsInvoiceCreateOut
from app.schemas.wheel import WheelPrizeOut, WheelSpinResultOut
from app.services import blackjack_engine as engine
from app.services import wheel_service
from app.services.game_config_service import get_config
from app.services.stars_payment_service import _request_telegram_invoice_link
from app.services.wallet_service import credit_coins, lock_user_for_update

# Outcome probabilities per paid entry, draws folded out (a draw replays for
# free): 400k-hand simulation of blackjack_engine with a basic hit/stand
# strategy — raw rates 4.6% natural, 39.2% win, 8.5% push, 47.7% loss. A
# naive "hit below 17" player lands at ≈5.2% / 40.4% / 54.5%. Only used for
# the admin expected-value estimate, never for gameplay.
OUTCOME_ESTIMATE = {"jackpot": 0.050, "golden": 0.428, "loss": 0.522}

_REWARD_POOLS = {
    engine.OUTCOME_HAT_TRICK: [WheelPrizePool.jackpot, WheelPrizePool.golden, WheelPrizePool.regular],
    engine.OUTCOME_WIN: [WheelPrizePool.golden, WheelPrizePool.regular],
}


def _next_local_midnight_utc() -> datetime:
    tomorrow = local_today() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=app_timezone()).astimezone(timezone.utc)


def _is_today(moment: datetime | None) -> bool:
    return moment is not None and local_today(moment) == local_today()


def _today_counters(user: User) -> tuple[int, int]:
    """(free used, paid bought) for today without mutating the user — a
    stale day reads as zero."""
    if not _is_today(user.blackjack_day_reset_at):
        return 0, 0
    return user.blackjack_free_used_today, user.blackjack_paid_bought_today


def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    if not _is_today(user.blackjack_day_reset_at):
        user.blackjack_free_used_today = 0
        user.blackjack_paid_bought_today = 0
        user.blackjack_day_reset_at = datetime.now(timezone.utc)
        db.add(user)


def _require_enabled(config: GameConfig) -> None:
    if not config.blackjack_enabled:
        raise ConflictError("«21» сейчас недоступна", details={"reason": "disabled"})


# --- Serialization (the only place a match leaves the server) -------------


def _card_out(card: str) -> BlackjackCardOut:
    suit, rank = card.split(":", 1)
    return BlackjackCardOut(rank=rank, suit=suit)


async def _spin_for_match(db: AsyncSession, match_id: int) -> WheelSpin | None:
    result = await db.execute(
        select(WheelSpin)
        .where(WheelSpin.blackjack_match_id == match_id)
        .options(joinedload(WheelSpin.prize).joinedload(WheelPrize.pack).joinedload(Pack.rarity_probabilities))
    )
    return result.unique().scalar_one_or_none()


async def _match_out(db: AsyncSession, match: BlackjackMatch) -> BlackjackMatchOut:
    """Hides the bot's hole card and its total while the hand is in progress;
    the remaining deck is never serialized."""
    state = match.server_state
    player, dealer = state["player"], state["dealer"]
    finished = match.status == "finished"
    player_total, player_soft = engine.hand_value(player)
    if finished:
        dealer_cards = [_card_out(c) for c in dealer]
        dealer_total = engine.hand_value(dealer)[0]
    else:
        dealer_cards = [_card_out(dealer[0]), BlackjackCardOut(hidden=True)]
        dealer_total = engine.hand_value(dealer[:1])[0]

    prize = None
    if finished and match.reward_pool:
        spin = await _spin_for_match(db, match.id)
        if spin is not None:
            prize = WheelPrizeOut.model_validate(spin.prize)

    return BlackjackMatchOut(
        id=match.id, status=match.status, entry_source=match.entry_source,
        player_cards=[_card_out(c) for c in player], player_total=player_total, player_soft=player_soft,
        dealer_cards=dealer_cards, dealer_total=dealer_total,
        outcome=match.outcome, outcome_reason=match.outcome_reason, reward_pool=match.reward_pool,
        prize=prize, consolation_coins=match.consolation_coins,
        created_at=match.created_at, finished_at=match.finished_at,
    )


# --- Status ----------------------------------------------------------------


async def _active_match(db: AsyncSession, user_id: int) -> BlackjackMatch | None:
    result = await db.execute(
        select(BlackjackMatch).where(BlackjackMatch.user_id == user_id, BlackjackMatch.status == "in_progress")
    )
    return result.scalar_one_or_none()


async def get_status(db: AsyncSession, user: User) -> BlackjackStatusOut:
    config = await get_config(db)
    free_used, paid_bought = _today_counters(user)
    active = await _active_match(db, user.id)
    golden = await wheel_service._active_prizes(db, WheelPrizePool.golden)
    jackpot = await wheel_service._active_prizes(db, WheelPrizePool.jackpot)
    return BlackjackStatusOut(
        enabled=config.blackjack_enabled,
        free_per_day=config.blackjack_free_per_day,
        free_remaining=max(0, config.blackjack_free_per_day - free_used),
        paid_entries=user.blackjack_paid_entries,
        replay_entries=user.blackjack_replay_entries,
        paid_bought_today=paid_bought,
        paid_daily_limit=config.blackjack_paid_daily_limit,
        stars_cost=config.blackjack_stars_cost,
        consolation_coins=config.blackjack_consolation_coins,
        next_reset_at=_next_local_midnight_utc(),
        active_match=await _match_out(db, active) if active else None,
        golden_prizes=[WheelPrizeOut.model_validate(p) for p in golden],
        jackpot_prizes=[WheelPrizeOut.model_validate(p) for p in jackpot],
    )


# --- Playing ---------------------------------------------------------------


def _shuffled_deck() -> list[str]:
    # Indirection so tests can stack the deck.
    return engine.shuffled_deck()


def _consume_entry(config: GameConfig, user: User) -> str:
    if user.blackjack_free_used_today < config.blackjack_free_per_day:
        user.blackjack_free_used_today += 1
        return "free"
    if user.blackjack_replay_entries > 0:
        user.blackjack_replay_entries -= 1
        return "replay"
    if user.blackjack_paid_entries > 0:
        user.blackjack_paid_entries -= 1
        return "paid"
    raise ConflictError(
        "Попытки на сегодня закончились",
        details={"reason": "no_entries", "next_reset_at": _next_local_midnight_utc().isoformat()},
    )


async def start_match(db: AsyncSession, user: User) -> BlackjackActionOut:
    """Deals a new hand, or returns the one already in progress (a retried
    start must not burn a second entry)."""
    config = await get_config(db)
    _require_enabled(config)
    locked_user = await lock_user_for_update(db, user.id)

    active = await _active_match(db, locked_user.id)
    if active is not None:
        return BlackjackActionOut(match=await _match_out(db, active), new_balance=locked_user.balance)

    _ensure_daily_reset(db, locked_user)
    entry_source = _consume_entry(config, locked_user)
    db.add(locked_user)

    player, dealer, deck = engine.deal(_shuffled_deck())
    match = BlackjackMatch(
        user_id=locked_user.id, status="in_progress", entry_source=entry_source,
        server_state={"deck": deck, "player": player, "dealer": dealer},
    )
    db.add(match)
    try:
        await db.flush()
    except IntegrityError:
        # The partial unique index caught a concurrent start that slipped past
        # the check above (only possible without real row locks, e.g. SQLite).
        await db.rollback()
        raise ConflictError("Партия уже идёт") from None

    spin_result = None
    early = engine.initial_outcome(player, dealer)
    if early is not None:
        spin_result = await _settle(db, config, locked_user, match, *early)

    await db.commit()
    return BlackjackActionOut(match=await _match_out(db, match), new_balance=locked_user.balance, spin_result=spin_result)


async def _lock_own_match(db: AsyncSession, user_id: int, match_id: int) -> BlackjackMatch:
    result = await db.execute(
        select(BlackjackMatch)
        .where(BlackjackMatch.id == match_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if match is None or match.user_id != user_id:
        raise NotFoundError("Партия не найдена")
    return match


async def _finished_response(db: AsyncSession, user: User, match: BlackjackMatch) -> BlackjackActionOut:
    return BlackjackActionOut(match=await _match_out(db, match), new_balance=user.balance)


async def hit(db: AsyncSession, user: User, match_id: int) -> BlackjackActionOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    match = await _lock_own_match(db, locked_user.id, match_id)
    if match.status != "in_progress":
        # A retried request after the hand already ended — report, don't redo.
        return await _finished_response(db, locked_user, match)

    state = dict(match.server_state)
    deck, player = list(state["deck"]), list(state["player"])
    player.append(deck.pop(0))
    match.server_state = {**state, "deck": deck, "player": player}

    spin_result = None
    if engine.is_bust(player):
        spin_result = await _settle(db, config, locked_user, match, *engine.final_outcome(player, state["dealer"]))
    elif engine.hand_value(player)[0] == 21:
        spin_result = await _dealer_turn_and_settle(db, config, locked_user, match)

    db.add(match)
    await db.commit()
    return BlackjackActionOut(match=await _match_out(db, match), new_balance=locked_user.balance, spin_result=spin_result)


async def stand(db: AsyncSession, user: User, match_id: int) -> BlackjackActionOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    match = await _lock_own_match(db, locked_user.id, match_id)
    if match.status != "in_progress":
        return await _finished_response(db, locked_user, match)

    spin_result = await _dealer_turn_and_settle(db, config, locked_user, match)
    db.add(match)
    await db.commit()
    return BlackjackActionOut(match=await _match_out(db, match), new_balance=locked_user.balance, spin_result=spin_result)


async def _dealer_turn_and_settle(
    db: AsyncSession, config: GameConfig, user: User, match: BlackjackMatch,
) -> WheelSpinResultOut | None:
    state = match.server_state
    dealer, deck = engine.play_dealer(state["dealer"], state["deck"])
    match.server_state = {**state, "deck": deck, "dealer": dealer}
    return await _settle(db, config, user, match, *engine.final_outcome(state["player"], dealer))


async def _roll_reward(db: AsyncSession, outcome: str) -> tuple[WheelPrizePool, WheelPrize]:
    for pool in _REWARD_POOLS[outcome]:
        prizes = await wheel_service._active_prizes(db, pool)
        if prizes:
            return pool, await wheel_service._roll_prize(db, pool)
    raise ConflictError("Призы колеса не настроены — обратись в поддержку")


async def _settle(
    db: AsyncSession, config: GameConfig, user: User, match: BlackjackMatch, outcome: str, reason: str,
) -> WheelSpinResultOut | None:
    """Finishes the hand and pays it out. Caller holds the user + match row
    locks and has checked status == in_progress, so this runs once per
    match; WheelSpin.blackjack_match_id's UNIQUE is the DB-level backstop."""
    match.status = "finished"
    match.outcome = outcome
    match.outcome_reason = reason
    match.finished_at = datetime.now(timezone.utc)
    db.add(match)

    spin_result = None
    if outcome in _REWARD_POOLS:
        pool, prize = await _roll_reward(db, outcome)
        match.reward_pool = pool.value
        spin_result = await wheel_service._grant_prize(
            db, user, prize, WheelSpinSource.blackjack, blackjack_match_id=match.id,
        )
    elif outcome == engine.OUTCOME_PUSH:
        user.blackjack_replay_entries += 1
        db.add(user)
    elif config.blackjack_consolation_coins > 0:
        await credit_coins(
            db, user, config.blackjack_consolation_coins, TransactionType.blackjack_consolation,
            "«21»: утешительный приз", related_object_type="blackjack_match", related_object_id=match.id,
        )
        match.consolation_coins = config.blackjack_consolation_coins
        db.add(user)
    return spin_result


# --- Stars entries (delivered by stars_payment_service.deliver_payment) ----


async def create_entry_invoice(db: AsyncSession, user: User) -> StarsInvoiceCreateOut:
    config = await get_config(db)
    _require_enabled(config)
    if config.blackjack_paid_daily_limit <= 0 or config.blackjack_stars_cost <= 0:
        raise ConflictError("Платные попытки сейчас не продаются")
    _, paid_bought = _today_counters(user)
    if paid_bought >= config.blackjack_paid_daily_limit:
        raise ConflictError(
            "Лимит платных попыток на сегодня исчерпан",
            details={"reason": "paid_limit", "next_reset_at": _next_local_midnight_utc().isoformat()},
        )

    payload_token = secrets.token_urlsafe(16)
    stars = config.blackjack_stars_cost
    db.add(StarsInvoice(user_id=user.id, is_blackjack_entry=True, payload_token=payload_token, stars_amount=stars))
    await db.flush()
    invoice_link = await _request_telegram_invoice_link(
        payload_token, "«21»: попытка", "Одна партия «21: Добавленное время» против Тренера соперника", stars,
    )
    await db.commit()
    return StarsInvoiceCreateOut(invoice_link=invoice_link, payload_token=payload_token, stars_amount=stars)


async def validate_stars_entry(db: AsyncSession, invoice: StarsInvoice) -> tuple[bool, str]:
    """pre_checkout_query check — the last chance to refuse before Telegram
    charges, so the daily cap is enforced here (delivery never refuses)."""
    config = await get_config(db)
    if not config.blackjack_enabled or config.blackjack_paid_daily_limit <= 0:
        return False, "«21» сейчас недоступна"
    user = await db.get(User, invoice.user_id)
    if user is None:
        return False, "Unknown order"
    _, paid_bought = _today_counters(user)
    if paid_bought >= config.blackjack_paid_daily_limit:
        return False, "Лимит платных попыток на сегодня исчерпан"
    return True, ""


async def deliver_stars_entry(db: AsyncSession, user: User) -> dict:
    """Banks one paid entry. Runs under stars_payment_service's invoice row
    lock + completed_at check (so once per invoice); the payment is already
    taken, so no limit is re-checked here. The caller commits."""
    locked_user = await lock_user_for_update(db, user.id)
    _ensure_daily_reset(db, locked_user)
    locked_user.blackjack_paid_bought_today += 1
    locked_user.blackjack_paid_entries += 1
    db.add(locked_user)
    return {"kind": "entry", "paid_entries": locked_user.blackjack_paid_entries}
