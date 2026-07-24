import math
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card import UserCard
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.game import FreeKickClaimOut, FreeKickKickOut, FreeKickNextKickOut, FreeKickStartOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

TOTAL_KICKS = 3
CENTER = 50.0
ELAPSED_MS_TOLERANCE = 300

# tier thresholds, expressed as a multiple of half_width, and their coin multiplier
TIERS: list[tuple[float, str, float]] = [
    (0.35, "perfect", 3.0),
    (1.0, "good", 1.5),
    (2.0, "ok", 0.75),
]


def half_width_for_rating(rating: int) -> float:
    r = max(58, min(99, rating))
    return 4.0 + (r - 58) / (99 - 58) * (12.0 - 4.0)


def _position_at(period_ms: int, elapsed_ms: int) -> float:
    return CENTER + CENTER * math.sin(2 * math.pi * elapsed_ms / period_ms)


def _tier_and_coins(distance: float, half_width: float, base_stake: int) -> tuple[str, int]:
    for multiple, tier, coin_multiplier in TIERS:
        if distance <= half_width * multiple:
            return tier, round(base_stake * coin_multiplier)
    return "miss", 0


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.free_kick_attempts_reset_at) if user.free_kick_attempts_reset_at else None
    if reset_day != today:
        user.free_kick_rewarded_attempts_today = 0
        user.free_kick_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


def _roll_kick(config, half_width: float) -> dict:
    period_ms = random.randint(config.free_kick_period_min_ms, config.free_kick_period_max_ms)
    return {
        "period_ms": period_ms,
        "start_ts": datetime.now(timezone.utc).isoformat(),
        "half_width": half_width,
        "result_position": None,
        "tier": None,
        "coins": None,
    }


def _kick_out(kick_index: int, kick: dict) -> FreeKickNextKickOut:
    return FreeKickNextKickOut(
        kick_index=kick_index, period_ms=kick["period_ms"],
        start_ts=kick["start_ts"], half_width=kick["half_width"],
    )


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.free_kick_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.free_kick_hourly_attempts = 0
        user.free_kick_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User, user_card_id: int) -> FreeKickStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.free_kick_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.free_kick_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.free_kick_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)
    if locked_user.free_kick_rewarded_attempts_today >= config.free_kick_daily_limit:
        raise ConflictError(
            "Daily reward attempts for Free Kick exhausted; you can still play unrewarded",
            details={"daily_limit": config.free_kick_daily_limit},
        )

    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != locked_user.id:
        raise ForbiddenError("You can only use your own cards")

    half_width = half_width_for_rating(card.player.rating)
    first_kick = _roll_kick(config, half_width)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.free_kick, status=GameSessionStatus.in_progress,
        server_state={
            "player_rating": card.player.rating, "kicks": [first_kick],
            "current_kick_index": 0, "total_coins": 0,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return FreeKickStartOut(session_id=session.id, kick=_kick_out(0, first_kick))


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.free_kick:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def resolve_kick(db: AsyncSession, user: User, session_id: int, elapsed_ms: int) -> FreeKickKickOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    kicks = list(state["kicks"])
    index = state["current_kick_index"]
    kick = dict(kicks[index])
    if kick["result_position"] is not None:
        raise ConflictError("This kick has already been resolved")

    # The client reports how much time elapsed before it tapped, but a
    # tampered client could claim any value to always land on the sine
    # wave's center (a "perfect" hit). Clamp it to what the server actually
    # observed since the kick started, plus slack for real network latency.
    kick_started_at = ensure_aware(datetime.fromisoformat(kick["start_ts"]))
    server_elapsed_ms = (datetime.now(timezone.utc) - kick_started_at).total_seconds() * 1000
    elapsed_ms = min(max(0, elapsed_ms), server_elapsed_ms + ELAPSED_MS_TOLERANCE)

    position = _position_at(kick["period_ms"], max(0, elapsed_ms))
    distance = abs(position - CENTER)
    tier, coins = _tier_and_coins(distance, kick["half_width"], config.free_kick_base_stake)

    kick["result_position"] = position
    kick["tier"] = tier
    kick["coins"] = coins
    kicks[index] = kick
    state["total_coins"] += coins

    next_index = index + 1
    next_kick_out = None
    if next_index < TOTAL_KICKS:
        next_kick = _roll_kick(config, kick["half_width"])
        kicks.append(next_kick)
        state["current_kick_index"] = next_index
        next_kick_out = _kick_out(next_index, next_kick)
        is_finished = False
    else:
        is_finished = True
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = state["total_coins"]

    state["kicks"] = kicks
    session.server_state = state
    db.add(session)
    await db.commit()

    return FreeKickKickOut(
        tier=tier, coins_this_kick=coins, total_coins=state["total_coins"],
        is_finished=is_finished, next_kick=next_kick_out,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> FreeKickClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    if locked_user.free_kick_rewarded_attempts_today >= config.free_kick_daily_limit:
        raise ConflictError("Daily reward attempts for Free Kick exhausted")

    reward = 0 if locked_user.game_rewards_blocked else session.reward_coins
    session.is_rewarded = True
    locked_user.free_kick_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Штрафной удар", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return FreeKickClaimOut(reward_coins=reward, new_balance=locked_user.balance)
