import random
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import local_today
from app.models.club import Club
from app.models.club_card import ClubCard
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, GameType
from app.models.game import GameSession
from app.models.user import User
from app.schemas.club_penalty import (
    ClubPenaltyClaimOut,
    ClubPenaltyForfeitOut,
    ClubPenaltyKickOut,
    ClubPenaltyStartOut,
)
from app.services.club_budget_service import credit_club_budget
from app.services.club_game_limits_service import consume_club_game_slot
from app.services.club_service import _lock_club, _require_membership
from app.services.game_config_service import get_config
from app.services.penalty_service import PENALTY_ZONES, REGULATION_KICKS, _resolve_shot, player_miss_chance
from app.services.wallet_service import lock_user_for_update


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.club_penalty_attempts_reset_at) if user.club_penalty_attempts_reset_at else None
    if reset_day != today:
        user.club_penalty_rewarded_attempts_today = 0
        user.club_penalty_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def start_session(db: AsyncSession, user: User, club_card_id: int) -> ClubPenaltyStartOut:
    membership = await _require_membership(db, user.id)
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await consume_club_game_slot(db, locked_user, config)

    await _ensure_daily_reset(db, locked_user)

    result = await db.execute(
        select(ClubCard).where(ClubCard.id == club_card_id, ClubCard.club_id == membership.club_id)
    )
    card = result.scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.club_penalty, status=GameSessionStatus.in_progress,
        server_state={
            "club_id": membership.club_id, "selected_card_id": card.id, "player_rating": card.player.rating,
            "rounds": [], "player_score": 0, "bot_score": 0, "kicks_taken": 0, "sudden_death": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ClubPenaltyStartOut(session_id=session.id, player_rating=card.player.rating, first_kicker="player")


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.club_penalty:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _current_kicker(state: dict) -> str:
    return "player" if state["kicks_taken"] % 2 == 0 else "bot"


def _apply_finish(session: GameSession, state: dict, result: str, config) -> None:
    """Shared by a natural finish (resolve_kick) and an explicit forfeit — marks the
    session finished with the given result and its reward. Unlike personal Penalty, no
    rating/league/task hooks: club mini-games stay decoupled from the personal track,
    same as club_game_service. session.status is always
    GameSessionStatus.won regardless of win/loss — mirrors penalty_service.py's own
    quirk exactly ("won" means "finished, reward claimable", not "the player won"; the
    real outcome lives in state["result"])."""
    state["result"] = result
    session.server_state = state
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = {
        "win": config.club_penalty_reward_win, "loss": config.club_penalty_reward_loss,
    }[result]


async def resolve_kick(db: AsyncSession, user: User, session_id: int, direction: str) -> ClubPenaltyKickOut:
    if direction not in PENALTY_ZONES:
        raise ConflictError("Invalid direction")

    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    kicker = _current_kicker(state)

    if kicker == "player":
        bot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(player_miss_chance(state["player_rating"]), direction, bot_dir)
        if outcome == "goal":
            state["player_score"] += 1
        round_entry = {
            "kicker": "player", "player_direction": direction, "bot_direction": bot_dir, "outcome": outcome,
        }
    else:
        bot_shot_dir = random.choice(PENALTY_ZONES)
        outcome = _resolve_shot(float(config.club_penalty_bot_miss_chance), bot_shot_dir, direction)
        if outcome == "goal":
            state["bot_score"] += 1
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
        _apply_finish(session, state, result, config)

    db.add(session)
    await db.commit()

    next_kicker = None if is_finished else _current_kicker(state)
    return ClubPenaltyKickOut(
        session_id=session.id, kicker=kicker, outcome=outcome,
        player_direction=direction, bot_direction=round_entry["bot_direction"],
        player_score=state["player_score"], bot_score=state["bot_score"],
        next_kicker=next_kicker, is_finished=is_finished, result=result,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> ClubPenaltyClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.club_penalty_rewarded_attempts_today >= config.club_penalty_daily_reward_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.club_penalty_rewarded_attempts_today += 1
    db.add(locked_user)
    db.add(session)

    club_id = (session.server_state or {}).get("club_id")
    new_budget = None
    if reward > 0 and club_id is not None:
        club = await _lock_club(db, club_id)
        if club is not None and not club.is_disbanded:
            await credit_club_budget(
                db, club, reward, ClubBudgetTransactionType.club_penalty_reward,
                f"Пенальти: {user.username or user.first_name or f'#{user.id}'}",
                related_object_type="game_session", related_object_id=session.id,
            )
            new_budget = club.budget
        else:
            reward = 0

    await db.commit()

    if new_budget is None and club_id is not None:
        club = await db.get(Club, club_id)
        new_budget = club.budget if club is not None else 0

    return ClubPenaltyClaimOut(
        reward_coins=reward, new_club_budget=new_budget or 0, daily_cap_reached=daily_cap_reached,
        result=session.server_state["result"],
    )


async def forfeit_session(db: AsyncSession, user: User, session_id: int) -> ClubPenaltyForfeitOut:
    """Immediately ends an in-progress session as a loss for the player, regardless of
    the partial score — mirrors penalty_service.forfeit_session's same rule. Called from
    the frontend's leave-confirmation dialog (matchGuardStore)."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session is not in progress")

    state = dict(session.server_state)
    _apply_finish(session, state, "loss", config)
    db.add(session)
    await db.commit()

    return ClubPenaltyForfeitOut(
        session_id=session.id, player_score=state["player_score"], bot_score=state["bot_score"], result="loss",
    )
