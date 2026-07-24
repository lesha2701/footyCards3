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
from app.schemas.game import PenaltyClaimOut, PenaltyKickOut, PenaltyStartOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

DIRECTIONS = ("left", "center", "right")
REGULATION_KICKS = 10  # 5 rounds x 2 kicks


def player_miss_chance(rating: int) -> float:
    r = max(58, min(99, rating))
    return 0.30 - (r - 58) / (99 - 58) * (0.30 - 0.05)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.penalty_attempts_reset_at) if user.penalty_attempts_reset_at else None
    if reset_day != today:
        user.penalty_rewarded_attempts_today = 0
        user.penalty_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.penalty_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.penalty_hourly_attempts = 0
        user.penalty_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User, user_card_id: int) -> PenaltyStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.penalty_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.penalty_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.penalty_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)
    if locked_user.penalty_rewarded_attempts_today >= config.penalty_daily_limit:
        raise ConflictError(
            "Daily reward attempts for Penalty exhausted; you can still play unrewarded",
            details={"daily_limit": config.penalty_daily_limit},
        )

    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != locked_user.id:
        raise ForbiddenError("You can only use your own cards")

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.penalty, status=GameSessionStatus.in_progress,
        server_state={
            "selected_card_id": card.id, "player_rating": card.player.rating,
            "rounds": [], "player_score": 0, "bot_score": 0, "kicks_taken": 0, "sudden_death": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return PenaltyStartOut(session_id=session.id, player_rating=card.player.rating, first_kicker="player")


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.penalty:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _current_kicker(state: dict) -> str:
    return "player" if state["kicks_taken"] % 2 == 0 else "bot"


async def resolve_kick(db: AsyncSession, user: User, session_id: int, direction: str) -> PenaltyKickOut:
    if direction not in DIRECTIONS:
        raise ConflictError("Invalid direction")

    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    kicker = _current_kicker(state)

    if kicker == "player":
        missed = random.random() < player_miss_chance(state["player_rating"])
        bot_dir = random.choice(DIRECTIONS)
        goal = (not missed) and (direction != bot_dir)
        if goal:
            state["player_score"] += 1
        outcome = "goal" if goal else ("miss" if missed else "saved")
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_missed = random.random() < float(config.penalty_bot_miss_chance)
        bot_shot_dir = random.choice(DIRECTIONS)
        saved = (not bot_missed) and (direction == bot_shot_dir)
        if not bot_missed and not saved:
            state["bot_score"] += 1
        outcome = "saved" if saved else ("miss" if bot_missed else "goal")
        round_entry = {
            "kicker": "bot", "player_direction": direction, "bot_direction": bot_shot_dir, "outcome": outcome,
        }

    state["rounds"] = list(state["rounds"]) + [round_entry]
    state["kicks_taken"] += 1

    is_finished = False
    result: str | None = None
    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0:
        if state["player_score"] != state["bot_score"]:
            is_finished = True
        else:
            state["sudden_death"] = True

    session.server_state = state
    if is_finished:
        result = "win" if state["player_score"] > state["bot_score"] else "loss"
        state["result"] = result
        session.server_state = state
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = {
            "win": config.penalty_reward_win, "loss": config.penalty_reward_loss,
        }[result]

    db.add(session)
    await db.commit()

    next_kicker = None if is_finished else _current_kicker(state)
    return PenaltyKickOut(
        session_id=session.id, kicker=kicker, outcome=outcome,
        player_direction=direction, bot_direction=round_entry["bot_direction"],
        player_score=state["player_score"], bot_score=state["bot_score"],
        next_kicker=next_kicker, is_finished=is_finished, result=result,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> PenaltyClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    if locked_user.penalty_rewarded_attempts_today >= config.penalty_daily_limit:
        raise ConflictError("Daily reward attempts for Penalty exhausted")

    reward = 0 if locked_user.game_rewards_blocked else session.reward_coins
    session.is_rewarded = True
    locked_user.penalty_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Пенальти", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return PenaltyClaimOut(reward_coins=reward, new_balance=locked_user.balance, result=session.server_state["result"])
