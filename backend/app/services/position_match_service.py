import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card_collection import CardCollection
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.player import Player
from app.models.user import User
from app.schemas.game import (
    PositionMatchAttemptOut,
    PositionMatchCardOut,
    PositionMatchClaimOut,
    PositionMatchStartOut,
)
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

CARDS_PER_ROUND = 5


def _active_filter():
    return (
        Player.is_active.is_(True),
        (CardCollection.is_active.is_(True)) | (Player.collection_id.is_(None)),
    )


async def _deal_cards(db: AsyncSession) -> list[Player]:
    """One active player per distinct position, so every card has exactly one
    correct match — a repeated position among the 5 would make the round
    ambiguous (two cards both correctly matching the same position label).
    Two-step (distinct positions, then one random player per chosen position)
    instead of a Postgres-only `DISTINCT ON` so this also runs on the SQLite
    test database."""
    positions_result = await db.execute(
        select(Player.position)
        .distinct()
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(*_active_filter())
    )
    available_positions = positions_result.scalars().all()
    if len(available_positions) < CARDS_PER_ROUND:
        raise ConflictError("Not enough active players configured for this game")
    chosen_positions = random.sample(available_positions, CARDS_PER_ROUND)

    players: list[Player] = []
    for position in chosen_positions:
        result = await db.execute(
            select(Player)
            .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
            .where(*_active_filter(), Player.position == position)
            .order_by(func.random())
            .limit(1)
        )
        players.append(result.scalar_one())
    random.shuffle(players)
    return players


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.position_match_attempts_reset_at) if user.position_match_attempts_reset_at else None
    if reset_day != today:
        user.position_match_rewarded_attempts_today = 0
        user.position_match_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.position_match_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.position_match_hourly_attempts = 0
        user.position_match_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> PositionMatchStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.position_match_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (
            datetime.now(timezone.utc) - ensure_aware(locked_user.position_match_hour_started_at)
        )
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.position_match_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    players = await _deal_cards(db)
    card_ids = [p.id for p in players]
    positions = [p.position.value for p in players]
    shuffled_positions = list(positions)
    random.shuffle(shuffled_positions)

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.position_match, status=GameSessionStatus.in_progress,
        server_state={
            "card_ids": card_ids,
            "positions_by_card_id": {str(p.id): p.position.value for p in players},
            "matched_player_ids": [],
            "mistakes": 0,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return PositionMatchStartOut(
        session_id=session.id,
        cards=[PositionMatchCardOut.model_validate(p) for p in players],
        positions=shuffled_positions,
        max_mistakes=config.position_match_max_mistakes,
    )


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.position_match:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _reward_for(mistakes: int, config) -> int:
    return max(config.position_match_reward_min, config.position_match_reward_perfect - mistakes * config.position_match_penalty_per_mistake)


async def submit_attempt(db: AsyncSession, user: User, session_id: int, player_id: int, position: str) -> PositionMatchAttemptOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    card_ids: list[int] = state["card_ids"]
    if player_id not in card_ids:
        raise ConflictError("This card is not part of this round")

    matched_player_ids: list[int] = list(state["matched_player_ids"])
    if player_id in matched_player_ids:
        raise ConflictError("This card has already been matched")

    correct_position = state["positions_by_card_id"][str(player_id)]
    is_correct = correct_position == position

    if is_correct:
        matched_player_ids.append(player_id)
        state["matched_player_ids"] = matched_player_ids
    else:
        state["mistakes"] = state["mistakes"] + 1

    mistakes = state["mistakes"]
    if len(matched_player_ids) == len(card_ids):
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = _reward_for(mistakes, config)
    elif mistakes >= config.position_match_max_mistakes:
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = 0

    session.server_state = state
    db.add(session)
    await db.commit()

    return PositionMatchAttemptOut(
        session_id=session.id, correct=is_correct, matched_player_ids=matched_player_ids,
        mistakes=mistakes, max_mistakes=config.position_match_max_mistakes, status=session.status.value,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> PositionMatchClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.position_match_rewarded_attempts_today >= config.position_match_daily_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.position_match_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Свою позицию", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return PositionMatchClaimOut(reward_coins=reward, new_balance=locked_user.balance)
