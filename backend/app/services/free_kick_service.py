import math
import random
import secrets
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
from app.schemas.game import (
    FreeKick3DKickOut,
    FreeKick3DShotOut,
    FreeKick3DShotRequest,
    FreeKick3DStartOut,
    FreeKickClaimOut,
    FreeKickKickOut,
    FreeKickNextKickOut,
    FreeKickStartOut,
)
from app.services import free_kick_3d_engine as engine
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update
from app.services.club_pass_service import extra_rewarded_attempts

TOTAL_KICKS = 3
MODE_3D = "3d"
# A swipe needs a human moment: a kick answered faster than this after the
# position was issued is refused (a bot replying instantly gains nothing).
MIN_3D_KICK_MS = 350
# Where a 3D goal counts as «в угол» (the corner/top bins), metres.
CORNER_X = engine.GOAL_HALF_WIDTH - 1.1
CORNER_Y = engine.GOAL_HEIGHT - 0.6
# Side spin (rad/s) from which a goal counts as curled.
CURL_SPIN = 20
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


async def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    await _ensure_hourly_reset(db, user)
    if user.free_kick_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(user.free_kick_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    user.free_kick_hourly_attempts += 1
    db.add(user)


async def _own_card(db: AsyncSession, user: User, user_card_id: int) -> UserCard:
    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != user.id:
        raise ForbiddenError("You can only use your own cards")
    return card


async def start_session(db: AsyncSession, user: User, user_card_id: int) -> FreeKickStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _take_hourly_attempt(db, locked_user, config.hourly_game_limit)

    await _ensure_daily_reset(db, locked_user)
    card = await _own_card(db, locked_user, user_card_id)

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
    # Two concurrent taps on one kick: the second waits here and sees it resolved.
    await db.refresh(session, with_for_update=True)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    if state.get("mode") == MODE_3D:
        raise ConflictError("This is a 3D free kick session")
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
    daily_cap_reached = locked_user.free_kick_rewarded_attempts_today >= config.free_kick_daily_limit + await extra_rewarded_attempts(
        db, locked_user.id, config
    )

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
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


# ---------------------------------------------------------------------------
# «Штрафной 3D» — the free kick mode now. A series of `free_kick_3d_kicks`
# positions (server-random seeds); each swipe is replayed here with the
# Python port of the client's engine, so the outcome and the coins are the
# server's alone. Same counters as the classic mode (its own hourly cap of
# series, the shared daily cap of rewarded series) and the same claim.
# ---------------------------------------------------------------------------

def _new_3d_kick() -> dict:
    return {
        "seed": secrets.randbelow(2**31 - 1) + 1,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "outcome": None,
        "coins": None,
    }


def score_3d_shot(config, result: engine.ShotResult) -> tuple[int, list[str]]:
    """Coins and bonus tags for one replayed shot."""
    if result.outcome == "goal":
        x, y, _ = result.end_position
        bonuses = []
        if abs(x) >= CORNER_X or y >= CORNER_Y:
            bonuses.append("corner")
        if abs(result.spin[1]) >= CURL_SPIN:
            bonuses.append("curl")
        coins = config.free_kick_3d_goal_coins
        coins += config.free_kick_3d_corner_bonus if "corner" in bonuses else 0
        coins += config.free_kick_3d_curl_bonus if "curl" in bonuses else 0
        return coins, bonuses
    if result.outcome == "save" or "post" in result.events:
        return config.free_kick_3d_near_coins, []
    return 0, []


async def start_3d(db: AsyncSession, user: User, user_card_id: int) -> FreeKick3DStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _take_hourly_attempt(db, locked_user, config.free_kick_hourly_limit)
    await _ensure_daily_reset(db, locked_user)
    card = await _own_card(db, locked_user, user_card_id)

    first = _new_3d_kick()
    total = max(1, config.free_kick_3d_kicks)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.free_kick, status=GameSessionStatus.in_progress,
        server_state={
            "mode": MODE_3D, "player_rating": card.player.rating, "total_kicks": total,
            "kicks": [first], "current_kick_index": 0, "total_coins": 0,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return FreeKick3DStartOut(
        session_id=session.id, rating=card.player.rating, total_kicks=total,
        kick=FreeKick3DKickOut(kick_index=0, seed=first["seed"]),
    )


async def shoot_3d(db: AsyncSession, user: User, session_id: int, swipe: FreeKick3DShotRequest) -> FreeKick3DShotOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    # Two concurrent swipes on one kick: the second waits here and sees it taken.
    await db.refresh(session, with_for_update=True)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    state = dict(session.server_state)
    if state.get("mode") != MODE_3D:
        raise ConflictError("Not a 3D free kick session")

    kicks = list(state["kicks"])
    index = state["current_kick_index"]
    kick = dict(kicks[index])
    if kick["outcome"] is not None:
        raise ConflictError("This kick has already been taken")
    issued = ensure_aware(datetime.fromisoformat(kick["issued_at"]))
    if (datetime.now(timezone.utc) - issued).total_seconds() * 1000 < MIN_3D_KICK_MS:
        raise ConflictError("Too fast — take your time to aim")

    result = engine.simulate_shot(
        engine.create_setup(kick["seed"], state["player_rating"]),
        engine.Swipe(swipe.dx, swipe.dy, swipe.curve, swipe.duration_ms),
    )
    coins, bonuses = score_3d_shot(config, result)
    kick.update(
        outcome=result.outcome, coins=coins, bonuses=bonuses,
        swipe={"dx": swipe.dx, "dy": swipe.dy, "curve": swipe.curve, "duration_ms": swipe.duration_ms},
    )
    kicks[index] = kick
    state["total_coins"] += coins

    next_out = None
    if index + 1 < state["total_kicks"]:
        nxt = _new_3d_kick()
        kicks.append(nxt)
        state["current_kick_index"] = index + 1
        next_out = FreeKick3DKickOut(kick_index=index + 1, seed=nxt["seed"])
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
    return FreeKick3DShotOut(
        outcome=result.outcome, bonuses=bonuses, coins_this_kick=coins, total_coins=state["total_coins"],
        is_finished=is_finished, next_kick=next_out,
    )
