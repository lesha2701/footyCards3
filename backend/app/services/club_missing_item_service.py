import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware, local_today
from app.models.club import Club
from app.models.enums import ClubBudgetTransactionType, GameSessionStatus, GameType
from app.models.game import GameSession, MissingItemRound
from app.models.user import User
from app.schemas.club_missing_item import (
    ClubMissingItemClaimOut,
    ClubMissingItemRevealOut,
    ClubMissingItemStartOut,
    ClubMissingItemSubmitOut,
)
from app.services.club_budget_service import credit_club_budget
from app.services.club_service import _lock_club, _require_membership
from app.services.game_config_service import get_config
from app.services.wallet_service import lock_user_for_update

# 20 distinct items — items within one round are always drawn without
# replacement (unlike club_game_service's ICONS, reused as a memorized
# ORDER where repeats are fine), so the pool size is also the hard cap on
# how many rounds the game can go before there's nothing left to add. Round R
# needs INITIAL_ITEM_COUNT + R - 1 distinct items.
ITEMS = ["⚽", "🥅", "🟨", "🟥", "👟", "🧤", "🏆", "🚩", "🎯", "🔥", "🧦", "📣", "🥇", "🥈", "🥉", "⏱️", "🏟️", "🌟", "🛡️", "⚡"]
INITIAL_ITEM_COUNT = 5
ANSWER_TIMEOUT_MS = 15000


def _hide_after_ms(round_number: int) -> int:
    return max(2000, 1800 + round_number * 300)


def _items_for_round(round_number: int) -> list[str]:
    return random.sample(ITEMS, INITIAL_ITEM_COUNT + round_number - 1)


async def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    today = local_today()
    reset_day = local_today(user.club_missing_item_attempts_reset_at) if user.club_missing_item_attempts_reset_at else None
    if reset_day != today:
        user.club_missing_item_rewarded_attempts_today = 0
        user.club_missing_item_attempts_reset_at = datetime.now(timezone.utc)
        db.add(user)


async def _ensure_hourly_reset(db: AsyncSession, user: User) -> None:
    now = datetime.now(timezone.utc)
    started = user.club_missing_item_hour_started_at
    if started is None or now - ensure_aware(started) >= timedelta(hours=1):
        user.club_missing_item_hourly_attempts = 0
        user.club_missing_item_hour_started_at = now
        db.add(user)


async def start_session(db: AsyncSession, user: User) -> ClubMissingItemStartOut:
    membership = await _require_membership(db, user.id)
    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await _ensure_hourly_reset(db, locked_user)
    if locked_user.club_missing_item_hourly_attempts >= config.club_missing_item_hourly_limit:
        remaining = timedelta(hours=1) - (
            datetime.now(timezone.utc) - ensure_aware(locked_user.club_missing_item_hour_started_at)
        )
        raise ConflictError(
            "Hourly play limit reached for this game",
            details={
                "hourly_limit": config.club_missing_item_hourly_limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    locked_user.club_missing_item_hourly_attempts += 1
    db.add(locked_user)

    await _ensure_daily_reset(db, locked_user)

    session = GameSession(
        user_id=locked_user.id, game_type=GameType.club_missing_item, status=GameSessionStatus.in_progress,
        server_state={"club_id": membership.club_id},
    )
    db.add(session)
    await db.flush()

    items = _items_for_round(1)
    round_ = MissingItemRound(session_id=session.id, round_number=1, items=",".join(items))
    db.add(round_)
    await db.commit()

    return ClubMissingItemStartOut(session_id=session.id, round_number=1, items=items)


async def _get_session(db: AsyncSession, user_id: int, session_id: int) -> GameSession:
    session = await db.get(GameSession, session_id)
    if not session or session.game_type != GameType.club_missing_item:
        raise NotFoundError("Game session not found")
    if session.user_id != user_id:
        raise ForbiddenError("This session does not belong to you")
    return session


async def _current_round(db: AsyncSession, session_id: int) -> MissingItemRound:
    result = await db.execute(
        select(MissingItemRound).where(MissingItemRound.session_id == session_id).order_by(MissingItemRound.round_number.desc()).limit(1)
    )
    return result.scalar_one()


async def reveal_round(db: AsyncSession, user: User, session_id: int) -> ClubMissingItemRevealOut:
    """Player pressed "Запомнил" — server picks (and keeps secret) which item
    to remove, then hands back the other N-1 items reshuffled for the brief
    "what's missing" flash before the client hides them and shows answer
    buttons for all N original items."""
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    round_ = await _current_round(db, session.id)
    if round_.removed_item is not None:
        raise ConflictError("This round has already been revealed")

    items = round_.items.split(",")
    removed_index = random.randrange(len(items))
    removed = items[removed_index]
    remaining = items[:removed_index] + items[removed_index + 1 :]
    random.shuffle(remaining)

    round_.removed_item = removed
    db.add(round_)
    await db.commit()

    return ClubMissingItemRevealOut(
        session_id=session.id, round_number=round_.round_number, items_shown=remaining,
        hide_after_ms=_hide_after_ms(round_.round_number), answer_timeout_ms=ANSWER_TIMEOUT_MS,
    )


async def submit_round(db: AsyncSession, user: User, session_id: int, answer: str) -> ClubMissingItemSubmitOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")

    round_ = await _current_round(db, session.id)
    if round_.removed_item is None:
        raise ConflictError("Press \"Запомнил\" before answering")

    correct = answer == round_.removed_item
    round_.was_correct = correct

    if not correct:
        session.status = GameSessionStatus.lost
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = min(session.score, config.club_missing_item_reward_cap)
        await db.commit()
        return ClubMissingItemSubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)

    session.score += round_.round_number * 10
    next_round_number = round_.round_number + 1
    next_item_count = INITIAL_ITEM_COUNT + next_round_number - 1

    if next_item_count > len(ITEMS):
        # Exhausted the item pool — there's nothing left to add, so this is a clean win
        # rather than an error. Same reward calc as a loss/voluntary end.
        session.status = GameSessionStatus.won
        session.finished_at = datetime.now(timezone.utc)
        session.reward_coins = min(session.score, config.club_missing_item_reward_cap)
        db.add(session)
        await db.commit()
        return ClubMissingItemSubmitOut(correct=True, session_id=session.id, score=session.score, status=session.status.value)

    next_items = _items_for_round(next_round_number)
    next_round = MissingItemRound(session_id=session.id, round_number=next_round_number, items=",".join(next_items))
    db.add(next_round)
    await db.commit()

    return ClubMissingItemSubmitOut(
        correct=True, session_id=session.id, score=session.score, status=session.status.value,
        next_round=ClubMissingItemStartOut(session_id=session.id, round_number=next_round_number, items=next_items),
    )


async def end_session(db: AsyncSession, user: User, session_id: int) -> ClubMissingItemSubmitOut:
    """Lets the player voluntarily stop and bank the current score."""
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status != GameSessionStatus.in_progress:
        raise ConflictError("This game session has already finished")
    session.status = GameSessionStatus.lost
    session.finished_at = datetime.now(timezone.utc)
    session.reward_coins = min(session.score, config.club_missing_item_reward_cap)
    await db.commit()
    return ClubMissingItemSubmitOut(correct=False, session_id=session.id, score=session.score, status=session.status.value)


async def claim_reward(db: AsyncSession, user: User, session_id: int) -> ClubMissingItemClaimOut:
    config = await get_config(db)
    session = await _get_session(db, user.id, session_id)
    if session.status not in (GameSessionStatus.lost, GameSessionStatus.won):
        raise ConflictError("Session is still in progress")

    locked_user = await lock_user_for_update(db, user.id)
    # Re-read the session under a row lock so a concurrent claim on the same
    # session can't race past this check before either commits — same
    # reasoning as club_game_service.claim_reward.
    await db.refresh(session, with_for_update=True)
    if session.is_rewarded:
        raise ConflictError("Reward for this session has already been claimed")
    await _ensure_daily_reset(db, locked_user)
    daily_cap_reached = locked_user.club_missing_item_rewarded_attempts_today >= config.club_missing_item_daily_reward_limit

    reward = 0 if (locked_user.game_rewards_blocked or daily_cap_reached) else min(session.score, config.club_missing_item_reward_cap)
    session.is_rewarded = True
    session.status = GameSessionStatus.rewarded
    if not daily_cap_reached:
        locked_user.club_missing_item_rewarded_attempts_today += 1
    db.add(locked_user)
    db.add(session)

    club_id = (session.server_state or {}).get("club_id")
    new_budget = None
    if reward > 0 and club_id is not None:
        club = await _lock_club(db, club_id)
        if club is not None and not club.is_disbanded:
            await credit_club_budget(
                db, club, reward, ClubBudgetTransactionType.club_missing_item_reward,
                f"Что исчезло?: {user.username or user.first_name or f'#{user.id}'}",
                related_object_type="game_session", related_object_id=session.id,
            )
            new_budget = club.budget
        else:
            reward = 0

    await db.commit()

    if new_budget is None and club_id is not None:
        club = await db.get(Club, club_id)
        new_budget = club.budget if club is not None else 0

    return ClubMissingItemClaimOut(reward_coins=reward, new_club_budget=new_budget or 0)
