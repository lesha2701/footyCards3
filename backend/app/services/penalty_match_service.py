import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.enums import MatchResult, NotificationType, PenaltyMatchStatus, PenaltyOpponentType
from app.models.penalty import PenaltyMatch, PenaltyQueueEntry
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
        opponent_type=match.opponent_type,
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


async def _finish_match(db: AsyncSession, match: PenaltyMatch, state: dict, forced_loser: Optional[str] = None) -> None:
    if forced_loser == "user":
        # Forfeit — always counts as a loss for the forfeiting side
        # regardless of the score so far, same rule Tactico's forfeit
        # enforces: leaving mid-match is never a safer bet than finishing.
        result, user_delta = MatchResult.loss, -1
    elif forced_loser == "opponent":
        result, user_delta = MatchResult.win, 3
    elif match.user_score > match.opponent_score:
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


async def forfeit_match(db: AsyncSession, user: User, match_id: int) -> PenaltyMatchOut:
    """Immediately ends an in-progress match as a loss for the forfeiting
    side, mirroring tactico_service.forfeit_match. Called from the
    frontend's leave-confirmation dialog (matchGuardStore) — without this,
    switching tabs mid-match and confirming "leave" would cost nothing."""
    match = await _lock_match(db, match_id)
    if user.id not in (match.user_id, match.opponent_user_id):
        raise ForbiddenError("You are not part of this match")
    if match.status != PenaltyMatchStatus.in_progress:
        raise ConflictError("This match is not in progress")

    state = dict(match.server_state or {})
    forfeiting_side = "user" if user.id == match.user_id else "opponent"
    await _finish_match(db, match, state, forced_loser=forfeiting_side)
    await db.commit()
    await db.refresh(match)
    return await _hydrate_match(db, match, user)


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


# ---------------------------------------------------------------------------
# Matchmaking
# ---------------------------------------------------------------------------

MATCHMAKING_TIMEOUT_SECONDS = 60


async def start_search(db: AsyncSession, user: User, user_card_id: int) -> PenaltyQueueEntry:
    if await _has_active_match(db, user.id):
        raise ConflictError("У тебя уже есть матч в процессе — заверши его, прежде чем искать нового соперника")

    result = await db.execute(
        select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # A queue row only ever gets cleaned up by its owner's own poll (see
        # get_search_status's two delete branches) or an explicit
        # cancel_search — a client that stops polling mid-search (page
        # refresh re-POSTing search, a backgrounded Telegram WebView, a
        # dropped connection) would otherwise leave an orphaned row behind
        # that unconditionally 409s every future search attempt forever.
        # Reclaim it instead: a row already matched (the owner never came
        # back to observe it) or one that's aged past the matchmaking
        # window is safe to replace with a fresh search.
        reclaimable = (
            existing.matched_match_id is not None
            or datetime.now(timezone.utc) - ensure_aware(existing.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS)
        )
        if not reclaimable:
            raise ConflictError("Ты уже ищешь соперника")
        await db.delete(existing)
        await db.flush()

    await _load_owned_card(db, user, user_card_id)

    # Non-consuming precondition check, mirroring _consume_hourly_slot's own
    # check exactly (same error shape, so the frontend's existing
    # formatGameError special-case for details.hourly_limit already renders
    # the right message) — but this does NOT increment the counter. A
    # player over their hourly limit shouldn't be allowed to join the queue
    # at all and burn the full 60s (or get silently dropped as stale the
    # moment a candidate appears); actual slot consumption still only
    # happens in get_search_status, at real pairing time.
    config = await get_config(db)
    from app.services.penalty_service import _ensure_hourly_reset

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
    db.add(locked_user)

    entry = PenaltyQueueEntry(user_id=user.id, user_card_id=user_card_id)
    db.add(entry)
    try:
        await db.commit()
    except IntegrityError:
        # A genuinely concurrent duplicate search request from the same user
        # (e.g. a retried network call) lost the race for the unique
        # constraint on user_id — surface it as the same clean 409 rather
        # than a raw 500.
        await db.rollback()
        raise ConflictError("Ты уже ищешь соперника")
    await db.refresh(entry)
    return entry


async def get_search_status(db: AsyncSession, user: User) -> tuple[str, Optional[int]]:
    """Also *is* the pairing attempt — every poller tries to pair itself
    with the oldest other waiting entry. Mirrors tactico_service's
    equivalent function, including its sorted-by-id lock ordering for the
    two User rows (see the comment below) so this stays consistent with
    _finish_match's `sorted([match.user_id, match.opponent_user_id])`
    pattern rather than locking "self, then candidate"."""
    result = await db.execute(
        select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    my_entry = result.scalar_one_or_none()
    if my_entry is None:
        return "not_searching", None

    if my_entry.matched_match_id is not None:
        # This row has done its job — the caller now has the match id in
        # hand — and start_search's "already searching" check doesn't
        # distinguish matched from unmatched rows, so leaving it around
        # would permanently block this player from ever searching again.
        # Delete it now that it's been observed (mirrors the pairing branch
        # below deleting the pairing caller's own row immediately, and
        # relies on this same branch to clean up the candidate's row the
        # first time *their* poll observes it).
        match_id = my_entry.matched_match_id
        await db.delete(my_entry)
        await db.commit()
        return "matched", match_id

    if datetime.now(timezone.utc) - ensure_aware(my_entry.created_at) > timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS):
        await db.delete(my_entry)
        await db.commit()
        return "timeout", None

    # Exclude entries older than the matchmaking window: without this cutoff
    # an abandoned/ghost row (owner stopped polling) is still a valid — and,
    # being the oldest, *preferred* — pairing candidate, so a live searcher
    # would get paired with a ghost that never resolves instead of another
    # live searcher.
    #
    # Note on SKIP LOCKED: two pollers whose requests overlap in the same
    # instant cannot pair with each other on that exact tick — each holds
    # FOR UPDATE on its own row (acquired above) for the duration of its own
    # transaction, making it invisible to the other's SKIP LOCKED scan here.
    # This self-resolves on the next ~2s poll and is what makes the
    # algorithm safe under concurrency, but it's non-obvious enough that a
    # future reader could otherwise expect symmetric same-tick pairing.
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MATCHMAKING_TIMEOUT_SECONDS)
    candidate_result = await db.execute(
        select(PenaltyQueueEntry)
        .where(
            PenaltyQueueEntry.user_id != user.id,
            PenaltyQueueEntry.matched_match_id.is_(None),
            PenaltyQueueEntry.created_at > cutoff,
        )
        .order_by(PenaltyQueueEntry.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    candidate = candidate_result.scalar_one_or_none()
    if candidate is None:
        await db.commit()
        return "searching", None

    config = await get_config(db)

    async def _card_still_owned(card_id: int, owner_id: int) -> bool:
        card_result = await db.execute(select(UserCard).where(UserCard.id == card_id))
        card = card_result.scalar_one_or_none()
        return card is not None and card.owner_id == owner_id

    # Lock both user rows up front in sorted-by-id order — mirroring
    # _finish_match's exact `sorted([match.user_id, match.opponent_user_id])`
    # pattern — rather than "self, then candidate". Two concurrent pollers
    # pairing the same two users would otherwise lock them in opposite order
    # depending on which side is "self" for that particular request, which
    # is a textbook lock-order deadlock risk.
    first_id, second_id = sorted([user.id, candidate.user_id])
    first_locked = await lock_user_for_update(db, first_id)
    second_locked = await lock_user_for_update(db, second_id)
    locked_user = first_locked if first_locked.id == user.id else second_locked
    locked_candidate = first_locked if first_locked.id == candidate.user_id else second_locked

    from app.services.penalty_service import _ensure_hourly_reset

    await _ensure_hourly_reset(db, locked_user)
    await _ensure_hourly_reset(db, locked_candidate)
    db.add(locked_user)
    db.add(locked_candidate)

    # Re-validate everything right before creating the match — state may
    # have drifted while both entries sat in the queue. Each side is
    # checked independently; either, both, or neither may have gone stale.
    stale: list[PenaltyQueueEntry] = []
    if (
        await _has_active_match(db, user.id)
        or not await _card_still_owned(my_entry.user_card_id, user.id)
        or locked_user.penalty_hourly_attempts >= config.hourly_game_limit
    ):
        stale.append(my_entry)
    if (
        await _has_active_match(db, candidate.user_id)
        or not await _card_still_owned(candidate.user_card_id, candidate.user_id)
        or locked_candidate.penalty_hourly_attempts >= config.hourly_game_limit
    ):
        stale.append(candidate)
    if stale:
        for entry in stale:
            await db.delete(entry)
        await db.commit()
        return ("not_searching" if my_entry in stale else "searching"), None

    locked_user.penalty_hourly_attempts += 1
    locked_candidate.penalty_hourly_attempts += 1
    db.add(locked_user)
    db.add(locked_candidate)

    now = datetime.now(timezone.utc)
    # Both players sit through a ~3s mandatory reveal screen before reaching
    # the match page, and the candidate specifically only discovers the
    # match via their own next status poll (up to ~2s later) — without this
    # margin the 10s first-kick clock could be half gone, or expired
    # entirely, before the candidate even arrives.
    FIRST_KICK_MARGIN_SECONDS = 8
    match = PenaltyMatch(
        user_id=locked_user.id,
        opponent_user_id=locked_candidate.id,
        opponent_name=locked_candidate.full_display_name(),
        user_card_id=my_entry.user_card_id,
        opponent_card_id=candidate.user_card_id,
        opponent_type=PenaltyOpponentType.online,
        status=PenaltyMatchStatus.in_progress,
        server_state={
            "kicks_taken": 0, "kicker": "user", "rounds": [],
            "user_score": 0, "opponent_score": 0,
            "user_pending_zone": None, "opponent_pending_zone": None,
            "kick_deadline": (now + timedelta(seconds=FIRST_KICK_MARGIN_SECONDS + KICK_TIMEOUT_SECONDS)).isoformat(),
            "match_deadline": (now + timedelta(seconds=MATCH_TIMEOUT_SECONDS)).isoformat(),
        },
    )
    db.add(match)
    await db.flush()

    # The pairing caller (this request's `user`) already has match.id in
    # hand and is about to return it directly — their row can be deleted
    # right now. The candidate hasn't observed the match yet (they'll learn
    # about it on their own next poll, via the `matched_match_id is not
    # None` branch above), so their row must stay — with matched_match_id
    # set — until then.
    candidate.matched_match_id = match.id
    db.add(candidate)
    await db.delete(my_entry)

    # Unlike the friend-challenge flows, the candidate side of a matchmaking
    # pairing has no other signal that a match now exists — if they've left
    # the search screen they'd otherwise have no way to learn about it
    # (it would silently resolve as a loss via the timeout sweep instead).
    # No dedicated "match started" notification type exists for Penalty;
    # reuse penalty_challenge_accepted (already reused elsewhere in this
    # file for more than its literal name suggests, e.g. _finish_match's
    # "Пенальти завершены" notifications) rather than adding a new enum
    # member for this fix wave.
    await notify(
        db, candidate.user_id, NotificationType.penalty_challenge_accepted,
        "Соперник найден!", "Начинается серия пенальти — не пропусти первый удар.",
        "penalty_match", match.id,
    )

    await db.commit()
    return "matched", match.id


async def cancel_search(db: AsyncSession, user: User) -> None:
    result = await db.execute(
        select(PenaltyQueueEntry).where(PenaltyQueueEntry.user_id == user.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise NotFoundError("Ты не ищешь соперника")
    if entry.matched_match_id is not None:
        raise ConflictError("Соперник уже найден — матч начинается")
    await db.delete(entry)
    await db.commit()
