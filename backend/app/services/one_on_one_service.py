"""«Атака 1 на 1»: a series of `one_on_one_attacks` episodes (server-random
seeds) — run at the keeper with the ball, one feint, a shot. The client sends
only the input timeline of each attack; it is replayed here with the Python
port of the client's engine (one_on_one_engine), so the outcome and the coins
are the server's alone. The usual counters: the shared hourly cap of series
(`hourly_game_limit`) and a daily cap of rewarded series — past it the
player keeps playing for nothing.
"""

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
    OneOnOneAttackOut,
    OneOnOneAttackRequest,
    OneOnOneClaimOut,
    OneOnOneResultOut,
    OneOnOneStartOut,
)
from app.services import my_player_service
from app.services import one_on_one_engine as engine
from app.services.club_pass_service import extra_rewarded_attempts
from app.services.free_kick_3d_engine import Swipe
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

# An attack can't be answered sooner than it takes to play: the replay's
# ticks in real time, less this much slack (the client's clock vs ours).
ELAPSED_SLACK_MS = 400


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.one_on_one_attempts_reset_at) if user.one_on_one_attempts_reset_at else None
    if reset_day != today:
        user.one_on_one_rewarded_attempts_today = 0
        user.one_on_one_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    now = datetime.now(timezone.utc)
    started = user.one_on_one_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.one_on_one_hourly_attempts = 0
        user.one_on_one_hour_started_at = now
    if user.one_on_one_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (now - ensure_aware(user.one_on_one_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={"hourly_limit": limit, "retry_after_seconds": max(0, int(remaining.total_seconds()))},
        )
    user.one_on_one_hourly_attempts += 1
    db.add(user)


async def _own_card(db: AsyncSession, user: User, user_card_id: int) -> UserCard:
    result = await db.execute(select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player)))
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != user.id:
        raise ForbiddenError("You can only use your own cards")
    return card


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.one_on_one:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _new_attack() -> dict:
    return {
        "seed": secrets.randbelow(2**31 - 1) + 1,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "outcome": None,
        "coins": None,
    }


def to_timeline(payload: OneOnOneAttackRequest) -> engine.Timeline:
    shot = payload.shot
    return engine.Timeline(
        controls=[(c[0], c[1], c[2]) for c in payload.controls],
        feint=(payload.feint.tick, payload.feint.dir) if payload.feint else None,
        shot=(shot.tick, Swipe(shot.dx, shot.dy, shot.curve, shot.duration_ms)) if shot else None,
    )


def score_attack(config, result: engine.EpisodeEnd) -> tuple[int, list[str]]:
    """Coins and bonus tags for one replayed attack."""
    if result.outcome == "goal":
        bonuses = []
        if result.feint == "bit":
            bonuses.append("feint")
        if result.chip:
            bonuses.append("chip")
        coins = config.one_on_one_goal_coins
        coins += config.one_on_one_feint_bonus if "feint" in bonuses else 0
        coins += config.one_on_one_chip_bonus if "chip" in bonuses else 0
        return coins, bonuses
    if result.outcome == "save" or (result.flight is not None and "post" in result.flight.events):
        return config.one_on_one_near_coins, []
    return 0, []


async def start(db: AsyncSession, user: User, user_card_id: int) -> OneOnOneStartOut:
    config = await get_config(db)
    locked = await lock_user_for_update(db, user.id)
    await _take_hourly_attempt(db, locked, config.hourly_game_limit)
    await _ensure_daily_reset(db, locked)
    card = await _own_card(db, locked, user_card_id)

    first = _new_attack()
    total = max(1, config.one_on_one_attacks)
    session = GameSession(
        user_id=locked.id, game_type=GameType.one_on_one, status=GameSessionStatus.in_progress,
        server_state={
            "player_rating": card.player.rating, "total_attacks": total,
            "attacks": [first], "current_index": 0, "total_coins": 0,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return OneOnOneStartOut(
        session_id=session.id, rating=card.player.rating, total_attacks=total,
        attack=OneOnOneAttackOut(attack_index=0, seed=first["seed"]),
        **await my_player_service.game_gear(db, locked.id),
    )


async def play_attack(db: AsyncSession, user: User, session_id: int, payload: OneOnOneAttackRequest) -> OneOnOneResultOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    # Two concurrent submissions of one attack: the second waits here and sees it taken.
    await db.refresh(session, with_for_update=True)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    attacks = list(state["attacks"])
    index = state["current_index"]
    attack = dict(attacks[index])
    if attack["outcome"] is not None:
        raise ConflictError("This attack has already been played")

    result = engine.replay_episode(engine.create_episode(attack["seed"], state["player_rating"]), to_timeline(payload))
    issued = ensure_aware(datetime.fromisoformat(attack["issued_at"]))
    elapsed_ms = (datetime.now(timezone.utc) - issued).total_seconds() * 1000
    if elapsed_ms < result.tick * engine.TICK * 1000 - ELAPSED_SLACK_MS:
        raise ConflictError("Too fast — this attack couldn't have been played yet")

    coins, bonuses = score_attack(config, result)
    attack.update(
        outcome=result.outcome, coins=coins, bonuses=bonuses, feint=result.feint, ticks=result.tick,
        timeline=payload.model_dump(),
    )
    attacks[index] = attack
    state["total_coins"] += coins

    next_out = None
    if index + 1 < state["total_attacks"]:
        nxt = _new_attack()
        attacks.append(nxt)
        state["current_index"] = index + 1
        next_out = OneOnOneAttackOut(attack_index=index + 1, seed=nxt["seed"])
        is_finished = False
    else:
        is_finished = True
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = state["total_coins"]

    state["attacks"] = attacks
    session.server_state = state
    db.add(session)
    await db.commit()
    return OneOnOneResultOut(
        outcome=result.outcome, bonuses=bonuses, feint=result.feint, coins_this_attack=coins,
        total_coins=state["total_coins"], is_finished=is_finished, next_attack=next_out,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> OneOnOneClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked)
    daily_cap_reached = locked.one_on_one_rewarded_attempts_today >= config.one_on_one_daily_limit + await extra_rewarded_attempts(
        db, locked.id, config
    )

    reward = 0 if (locked.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked.one_on_one_rewarded_attempts_today += 1
    if reward > 0:
        await credit_coins(
            db, locked, reward, TransactionType.game_reward,
            "Награда за Атаку 1 на 1", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked)
    return OneOnOneClaimOut(reward_coins=reward, new_balance=locked.balance)
