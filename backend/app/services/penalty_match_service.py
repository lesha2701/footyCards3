from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
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


async def create_challenge(db: AsyncSession, sender: User, receiver_id: int, user_card_id: int) -> PenaltyMatchOut:
    config = await get_config(db)
    if receiver_id == sender.id:
        raise ConflictError("You cannot challenge yourself")
    receiver = await db.get(User, receiver_id)
    if not receiver:
        raise NotFoundError("User not found")
    if receiver.is_banned:
        raise ConflictError("This user is banned and cannot be challenged")
    await _load_owned_card(db, sender, user_card_id)

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
