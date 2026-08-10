import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.card_collection import CardCollection
from app.models.enums import GameSessionStatus, GameType, TransactionType
from app.models.game import GameSession
from app.models.player import Player
from app.models.user import User
from app.schemas.game import PairsCardOut, PairsClaimOut, PairsFlipOut, PairsStartOut
from app.schemas.player import PlayerOut
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

BOARD_SIZE = 25
TOTAL_PAIRS = 12


async def _deal_board(db: AsyncSession) -> list[Optional[int]]:
    """25-cell board: 12 player ids (each appearing twice) plus one `None`
    slot — the odd tile out of a 5x5 grid, a one-off bonus that resolves the
    instant it's flipped instead of needing a partner. Shuffled once at
    session start and never sent to the client in full; positions are only
    revealed as the player flips them (see flip_card)."""
    result = await db.execute(
        select(Player.id)
        .outerjoin(CardCollection, Player.collection_id == CardCollection.id)
        .where(Player.is_active.is_(True), (CardCollection.is_active.is_(True)) | (Player.collection_id.is_(None)))
        .order_by(func.random())
        .limit(TOTAL_PAIRS)
    )
    player_ids = [row[0] for row in result.all()]
    if len(player_ids) < TOTAL_PAIRS:
        raise ConflictError("Not enough active players configured for this game")

    board: list[Optional[int]] = player_ids * 2 + [None]
    random.shuffle(board)
    return board


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.pairs_attempts_reset_at) if user.pairs_attempts_reset_at else None
    if reset_day != today:
        user.pairs_rewarded_attempts_today = 0
        user.pairs_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.pairs_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.pairs_hourly_attempts = 0
        user.pairs_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> PairsStartOut:
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.pairs_hourly_attempts >= config.hourly_game_limit:
        remaining = timedelta(hours=1) - (datetime.now(timezone.utc) - ensure_aware(locked_user.pairs_hour_started_at))
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.hourly_game_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.pairs_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    board = await _deal_board(db)
    session = GameSession(
        user_id=locked_user.id, game_type=GameType.card_pairs, status=GameSessionStatus.in_progress,
        server_state={
            "board": board,
            "revealed_positions": [],
            "pending_position": None,
            "wrong_attempts": 0,
            "matched_pairs": 0,
            "bonus_found": False,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return PairsStartOut(session_id=session.id, board_size=BOARD_SIZE, total_pairs=TOTAL_PAIRS)


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.card_pairs:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


def _tiered_reward(wrong_attempts: int, config) -> int:
    """Reward drops a bracket for every `pairs_error_bracket_size` wrong
    attempts, e.g. with the defaults (perfect=40, bracket_size=10,
    bracket_penalty=10): 0-10 wrong -> 40 coins, 11-20 -> 30, 21-30 -> 20,
    ... floored at pairs_reward_min. A step function (not a per-mistake
    linear penalty) so a couple of extra slip-ups near a bracket boundary
    don't shave the reward down one coin at a time."""
    tier = 0 if wrong_attempts == 0 else (wrong_attempts - 1) // config.pairs_error_bracket_size
    return max(config.pairs_reward_min, config.pairs_reward_perfect - tier * config.pairs_bracket_penalty)


def _maybe_finish(session: GameSession, state: dict, config) -> None:
    """Ends the session once every one of the 25 tiles is revealed — all 12
    pairs matched *and* the bonus tile found, wherever in the run it turned
    up. Keying the win condition off `matched_pairs` alone would let a run
    finish before the bonus was ever seen if it happened to be the last tile
    still face-down."""
    if len(state["revealed_positions"]) < BOARD_SIZE:
        return
    session.status = GameSessionStatus.won
    session.finished_at = datetime.now(timezone.utc)
    reward = _tiered_reward(state["wrong_attempts"], config)
    if state["bonus_found"]:
        reward += config.pairs_bonus_coins
    session.reward_coins = reward


async def _card_out(db: AsyncSession, position: int, value: Optional[int]) -> PairsCardOut:
    if value is None:
        return PairsCardOut(position=position, is_bonus=True, player=None)
    player = await db.get(Player, value)
    return PairsCardOut(position=position, is_bonus=False, player=PlayerOut.model_validate(player))


async def flip_card(db: AsyncSession, user: User, session_id: int, position: int) -> PairsFlipOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    state = dict(session.server_state)
    board: list[Optional[int]] = state["board"]
    if position >= len(board):
        raise ConflictError("Invalid board position")

    revealed_positions: list[int] = list(state["revealed_positions"])
    if position in revealed_positions:
        raise ConflictError("This card is already revealed")

    pending_position: Optional[int] = state["pending_position"]
    if pending_position == position:
        raise ConflictError("Pick a different card")

    value = board[position]

    if value is None:
        # Bonus tile: resolves on its own, doesn't consume a pair attempt.
        revealed_positions.append(position)
        state["revealed_positions"] = revealed_positions
        state["bonus_found"] = True
        _maybe_finish(session, state, config)
        session.server_state = state
        db.add(session)
        await db.commit()

        card = await _card_out(db, position, value)
        return PairsFlipOut(
            session_id=session.id, revealed=[card], matched=True,
            matched_pairs=state["matched_pairs"], wrong_attempts=state["wrong_attempts"],
            total_pairs=TOTAL_PAIRS, status=session.status.value,
        )

    if pending_position is None:
        state["pending_position"] = position
        session.server_state = state
        db.add(session)
        await db.commit()

        card = await _card_out(db, position, value)
        return PairsFlipOut(
            session_id=session.id, revealed=[card], matched=None,
            matched_pairs=state["matched_pairs"], wrong_attempts=state["wrong_attempts"],
            total_pairs=TOTAL_PAIRS, status=session.status.value,
        )

    first_value = board[pending_position]
    matched = first_value == value
    state["pending_position"] = None
    if matched:
        revealed_positions.extend([pending_position, position])
        state["revealed_positions"] = revealed_positions
        state["matched_pairs"] = state["matched_pairs"] + 1
    else:
        state["wrong_attempts"] = state["wrong_attempts"] + 1

    _maybe_finish(session, state, config)

    session.server_state = state
    db.add(session)
    await db.commit()

    first_card = await _card_out(db, pending_position, first_value)
    second_card = await _card_out(db, position, value)
    return PairsFlipOut(
        session_id=session.id, revealed=[first_card, second_card], matched=matched,
        matched_pairs=state["matched_pairs"], wrong_attempts=state["wrong_attempts"],
        total_pairs=TOTAL_PAIRS, status=session.status.value,
    )


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> PairsClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.won:
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.pairs_rewarded_attempts_today >= config.pairs_daily_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else session.reward_coins
    session.is_rewarded = True
    if not daily_cap_reached:
        locked_user.pairs_rewarded_attempts_today += 1

    if reward > 0:
        await credit_coins(
            db, locked_user, reward, TransactionType.game_reward,
            "Награда за Найди пару", related_object_type="game_session", related_object_id=session.id,
        )
    db.add(session)
    await db.commit()
    await db.refresh(locked_user)

    return PairsClaimOut(reward_coins=reward, new_balance=locked_user.balance)
