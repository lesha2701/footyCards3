import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import MatchResult, NotificationType, PenaltyMatchStatus
from app.models.penalty import PenaltyMatch
from app.models.user import User
from app.schemas.penalty_match import PenaltyMatchOut, PenaltyRoundOut
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.penalty_service import PENALTY_ZONES, _resolve_shot
from app.services.wallet_service import lock_user_for_update

KICK_TIMEOUT_SECONDS = 10
MATCH_TIMEOUT_SECONDS = 180
REGULATION_KICKS = 10  # 5 rounds x 2 kicks, same as the bot mode

_FLIP_RESULT = {MatchResult.win: MatchResult.loss, MatchResult.loss: MatchResult.win, MatchResult.draw: MatchResult.draw}
_OPPONENT_RATING_DELTA = {3: -1, -1: 3, 1: 1}


async def _get_match_or_404(db: AsyncSession, match_id: int) -> PenaltyMatch:
    match = await db.get(PenaltyMatch, match_id)
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _lock_match(db: AsyncSession, match_id: int) -> PenaltyMatch:
    result = await db.execute(
        select(PenaltyMatch).where(PenaltyMatch.id == match_id)
        .with_for_update().execution_options(populate_existing=True)
    )
    match = result.scalar_one_or_none()
    if not match:
        raise NotFoundError("Match not found")
    return match


async def _load_owned_card(db: AsyncSession, user: User, user_card_id: int) -> UserCard:
    result = await db.execute(
        select(UserCard).where(UserCard.id == user_card_id).options(joinedload(UserCard.player))
    )
    card = result.unique().scalar_one_or_none()
    if not card:
        raise NotFoundError("Card not found")
    if card.owner_id != user.id:
        raise ForbiddenError("You can only use your own cards")
    return card


async def _has_active_match(db: AsyncSession, user_id: int, exclude_match_id: Optional[int] = None) -> bool:
    conditions = [
        or_(PenaltyMatch.user_id == user_id, PenaltyMatch.opponent_user_id == user_id),
        PenaltyMatch.status == PenaltyMatchStatus.in_progress,
    ]
    if exclude_match_id is not None:
        conditions.append(PenaltyMatch.id != exclude_match_id)
    result = await db.execute(select(PenaltyMatch.id).where(*conditions).limit(1))
    return result.scalar_one_or_none() is not None


async def _consume_hourly_slot(db: AsyncSession, user_id: int, config) -> User:
    from app.services.penalty_service import _ensure_hourly_reset

    locked_user = await lock_user_for_update(db, user_id)
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
    return locked_user


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int, user_card_id: int) -> PenaltyMatchOut:
    config = await get_config(db)
    if await _has_active_match(db, sender.id):
        raise ConflictError("У тебя уже есть матч в Пенальти в процессе — заверши его, прежде чем начать новый")
    if receiver_id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")
    await _load_owned_card(db, sender, user_card_id)

    sender = await _consume_hourly_slot(db, sender.id, config)

    match = PenaltyMatch(
        user_id=sender.id,
        opponent_user_id=receiver.id,
        opponent_name=receiver.full_display_name(),
        user_card_id=user_card_id,
        status=PenaltyMatchStatus.pending_accept,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=config.penalty_challenge_expiry_hours),
        server_state={
            "kicks_taken": 0, "kicker": "user", "rounds": [],
            "user_score": 0, "opponent_score": 0,
            "user_pending_zone": None, "opponent_pending_zone": None,
            "kick_deadline": None, "match_deadline": None,
        },
    )
    db.add(match)
    await db.flush()

    await notify(
        db, receiver.id, NotificationType.penalty_challenge_received,
        "Вызов на пенальти", f"{sender.full_display_name()} вызвал(а) вас на серию пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, sender)


async def accept_challenge(db: AsyncSession, user: User, match_id: int, user_card_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can accept this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")
    if match.expires_at and ensure_aware(match.expires_at) <= datetime.now(timezone.utc):
        match.status = PenaltyMatchStatus.expired
        match.resolved_at = datetime.now(timezone.utc)
        db.add(match)
        await db.commit()
        raise ConflictError("This challenge has expired")

    if await _has_active_match(db, user.id, exclude_match_id=match.id):
        raise ConflictError("У тебя уже есть матч в Пенальти в процессе — заверши его, прежде чем принять вызов")

    await _load_owned_card(db, user, user_card_id)

    now = datetime.now(timezone.utc)
    state = dict(match.server_state)
    state["kick_deadline"] = (now + timedelta(seconds=KICK_TIMEOUT_SECONDS)).isoformat()
    state["match_deadline"] = (now + timedelta(seconds=MATCH_TIMEOUT_SECONDS)).isoformat()
    match.server_state = state
    flag_modified(match, "server_state")
    match.opponent_card_id = user_card_id
    match.status = PenaltyMatchStatus.in_progress
    db.add(match)

    challenger = await db.get(User, match.user_id)
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_accepted,
        "Вызов принят", f"{user.full_display_name()} принял(а) ваш вызов на пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def decline_challenge(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.opponent_user_id != user.id:
        raise ForbiddenError("Only the challenged user can decline this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = PenaltyMatchStatus.declined
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_declined,
        "Вызов отклонён", f"{user.full_display_name()} отклонил(а) ваш вызов на пенальти.",
        "penalty_match", match.id,
    )
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def cancel_challenge(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    match = await _lock_match(db, match_id)
    if match.user_id != user.id:
        raise ForbiddenError("Only the challenger can cancel this challenge")
    if match.status != PenaltyMatchStatus.pending_accept:
        raise ConflictError("This challenge is no longer pending")

    match.status = PenaltyMatchStatus.cancelled
    match.resolved_at = datetime.now(timezone.utc)
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def _hydrate_match(db: AsyncSession, match: PenaltyMatch, viewer: User) -> PenaltyMatchOut:
    state = match.server_state or {}
    side = "user" if viewer.id == match.user_id else "opponent"
    other_side = "opponent" if side == "user" else "user"

    if side == "user":
        opponent_name = match.opponent_name
        opponent_user_id = match.opponent_user_id
        viewer_score, other_score = match.user_score, match.opponent_score
        result_out = match.result
        rating_delta = match.rating_delta
    else:
        challenger = await db.get(User, match.user_id)
        opponent_name = challenger.full_display_name() if challenger else match.opponent_name
        opponent_user_id = match.user_id
        viewer_score, other_score = match.opponent_score, match.user_score
        result_out = _FLIP_RESULT[match.result] if match.result else None
        rating_delta = state.get("opponent_rating_delta", 0)

    rounds_out = [
        PenaltyRoundOut(
            kicker=(r["kicker"] if r["kicker"] == side else other_side) if side == "user" else
                   ("user" if r["kicker"] == "opponent" else "opponent"),
            shot_zone=r["shot_zone"], dive_zone=r["dive_zone"], outcome=r["outcome"],
        )
        for r in state.get("rounds", [])
    ]

    kicker = state.get("kicker")
    kicker_out = kicker if side == "user" else ({"user": "opponent", "opponent": "user"}.get(kicker) if kicker else None)
    is_viewer_turn = (
        match.status == PenaltyMatchStatus.in_progress and state.get(f"{side}_pending_zone") is None
    )

    return PenaltyMatchOut(
        id=match.id,
        opponent_name=opponent_name,
        opponent_user_id=opponent_user_id,
        status=match.status,
        viewer_side=side,
        user_score=viewer_score,
        opponent_score=other_score,
        rounds=rounds_out,
        kicker=kicker_out,
        is_viewer_turn=is_viewer_turn,
        kick_deadline=ensure_aware(datetime.fromisoformat(state["kick_deadline"])) if state.get("kick_deadline") else None,
        match_deadline=ensure_aware(datetime.fromisoformat(state["match_deadline"])) if state.get("match_deadline") else None,
        result=result_out,
        rating_delta=rating_delta,
        created_at=match.created_at,
        expires_at=match.expires_at,
        resolved_at=match.resolved_at,
    )


def _current_kicker(state: dict) -> str:
    return state["kicker"]


async def submit_pick(db: AsyncSession, user: User, match_id: int, zone: str) -> PenaltyMatchOut:
    if zone not in PENALTY_ZONES:
        raise ConflictError("Invalid zone")
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != PenaltyMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")

    side = "user" if user.id == match.user_id else "opponent"
    state = dict(match.server_state)
    if state.get(f"{side}_pending_zone") is not None:
        raise ConflictError("You already picked for this kick")
    state[f"{side}_pending_zone"] = zone

    other_side = "opponent" if side == "user" else "user"
    if state.get(f"{other_side}_pending_zone") is not None:
        await _resolve_current_kick(db, match, state)
    else:
        state["kick_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=KICK_TIMEOUT_SECONDS)
        ).isoformat()

    match.server_state = state
    flag_modified(match, "server_state")
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


async def _resolve_current_kick(db: AsyncSession, match: PenaltyMatch, state: dict) -> None:
    """Both sides have a pending zone for the current kick — resolve it,
    record the round, advance to the next kicker, and finish the match if
    regulation is complete. Mutates `state` in place; caller still has to
    persist `match.server_state`/commit."""
    kicker = state["kicker"]
    defender = "opponent" if kicker == "user" else "user"
    shot_zone = state[f"{kicker}_pending_zone"]
    dive_zone = state[f"{defender}_pending_zone"]

    card_id = match.user_card_id if kicker == "user" else match.opponent_card_id
    card_result = await db.execute(select(UserCard).where(UserCard.id == card_id).options(joinedload(UserCard.player)))
    card = card_result.unique().scalar_one_or_none()
    miss_chance = 0.12 if card is None else _shooter_miss_chance(card.player.rating)

    outcome = _resolve_shot(miss_chance, shot_zone, dive_zone)
    if outcome == "goal":
        state[f"{kicker}_score"] += 1

    state["rounds"] = list(state["rounds"]) + [
        {"kicker": kicker, "shot_zone": shot_zone, "dive_zone": dive_zone, "outcome": outcome}
    ]
    state["kicks_taken"] += 1
    state["kicker"] = defender
    state["user_pending_zone"] = None
    state["opponent_pending_zone"] = None
    match.user_score, match.opponent_score = state["user_score"], state["opponent_score"]

    # Same as the solo bot mode (penalty_service.resolve_kick): a tie at
    # regulation continues into sudden death rather than finishing — per
    # the plan's Global Constraints, the only way a PvP match ends in a
    # draw is the 3-minute match clock cutting it short while still tied
    # (see _auto_resolve_overdue's match_deadline branch, which calls
    # _finish_match unconditionally). Sudden death here has no separate
    # "sudden_death" flag (unlike the solo mode) because it doesn't need
    # one: kicks just keep alternating past REGULATION_KICKS until the
    # score differs at an even kicks_taken, or the match clock ends it.
    if state["kicks_taken"] >= REGULATION_KICKS and state["kicks_taken"] % 2 == 0 and state["user_score"] != state["opponent_score"]:
        await _finish_match(db, match, state)
    else:
        state["kick_deadline"] = (
            datetime.now(timezone.utc) + timedelta(seconds=KICK_TIMEOUT_SECONDS)
        ).isoformat()


def _shooter_miss_chance(rating: int) -> float:
    from app.services.penalty_service import player_miss_chance
    return player_miss_chance(rating)


async def _finish_match(db: AsyncSession, match: PenaltyMatch, state: dict) -> None:
    if match.user_score > match.opponent_score:
        result, user_delta = MatchResult.win, 3
    elif match.user_score < match.opponent_score:
        result, user_delta = MatchResult.loss, -1
    else:
        result, user_delta = MatchResult.draw, 1
    opponent_delta = _OPPONENT_RATING_DELTA[user_delta]
    state["opponent_rating_delta"] = opponent_delta

    match.result = result
    match.rating_delta = user_delta
    match.status = PenaltyMatchStatus.finished
    match.resolved_at = datetime.now(timezone.utc)
    match.server_state = state
    flag_modified(match, "server_state")

    first_id, second_id = sorted([match.user_id, match.opponent_user_id])
    first_locked = await lock_user_for_update(db, first_id)
    second_locked = await lock_user_for_update(db, second_id)
    locked_user = first_locked if first_locked.id == match.user_id else second_locked
    locked_opponent = first_locked if first_locked.id == match.opponent_user_id else second_locked

    locked_user.penalty_rating = max(0, locked_user.penalty_rating + user_delta)
    locked_opponent.penalty_rating = max(0, locked_opponent.penalty_rating + opponent_delta)
    db.add(locked_user)
    db.add(locked_opponent)

    await notify(
        db, match.opponent_user_id, NotificationType.penalty_challenge_accepted,
        "Пенальти завершены",
        f"Серия с {locked_user.full_display_name()} завершена — результат: {_FLIP_RESULT[result].value}.",
        "penalty_match", match.id,
    )
    await notify(
        db, match.user_id, NotificationType.penalty_challenge_accepted,
        "Пенальти завершены",
        f"Серия с {locked_opponent.full_display_name()} завершена — результат: {result.value}.",
        "penalty_match", match.id,
    )
    db.add(match)


async def _auto_resolve_overdue(db: AsyncSession) -> int:
    """Lazy sweep, mirroring tactico_service._auto_play_overdue_rounds: runs
    opportunistically on every list_matches/get_match call rather than a
    background scheduler (see CLAUDE.md's turn-based-game-state note).

    Every match is re-locked via _lock_match (not just read) and its status
    re-checked before touching it — both players' clients poll every 2.5s,
    so multiple sweeps can and do run concurrently for the same overdue
    match; without the lock + re-check, two sweeps that both see
    in_progress would both reach _finish_match and double-award the rating
    delta (this is exactly the row-locking the plan's Global Constraints
    require for the timeout sweep, caught by the final whole-branch
    review)."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(PenaltyMatch.id).where(PenaltyMatch.status == PenaltyMatchStatus.in_progress))
    match_ids = result.scalars().all()
    swept = 0
    for match_id in match_ids:
        match = await _lock_match(db, match_id)
        if match.status != PenaltyMatchStatus.in_progress:
            continue  # resolved by a concurrent sweep (or a pick) while we waited for the lock
        state = dict(match.server_state or {})

        match_deadline = state.get("match_deadline")
        if match_deadline and ensure_aware(datetime.fromisoformat(match_deadline)) <= now:
            if state.get("user_pending_zone") is not None and state.get("opponent_pending_zone") is not None:
                await _resolve_current_kick(db, match, state)
            if match.status == PenaltyMatchStatus.in_progress:  # still in progress: end it on the current score
                await _finish_match(db, match, state)
            else:
                match.server_state = state
                flag_modified(match, "server_state")
                db.add(match)
            await db.commit()
            swept += 1
            continue

        kick_deadline = state.get("kick_deadline")
        if not kick_deadline or ensure_aware(datetime.fromisoformat(kick_deadline)) > now:
            continue

        for side in ("user", "opponent"):
            if state.get(f"{side}_pending_zone") is None:
                state[f"{side}_pending_zone"] = random.choice(PENALTY_ZONES)

        await _resolve_current_kick(db, match, state)
        match.server_state = state
        flag_modified(match, "server_state")
        db.add(match)
        await db.commit()
        swept += 1
    return swept


async def list_matches(db: AsyncSession, user: User) -> list[PenaltyMatchOut]:
    await _auto_resolve_overdue(db)
    result = await db.execute(
        select(PenaltyMatch)
        .where(or_(PenaltyMatch.user_id == user.id, PenaltyMatch.opponent_user_id == user.id))
        .order_by(PenaltyMatch.created_at.desc())
    )
    matches = result.scalars().all()
    return [await _hydrate_match(db, m, user) for m in matches]


async def get_match(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    await _auto_resolve_overdue(db)
    match = await _get_match_or_404(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    await db.refresh(match)
    return await _hydrate_match(db, match, user)
