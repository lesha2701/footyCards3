"""Counts of things waiting on the player, for the bottom-nav badges: one
cheap request instead of every tab fetching full match/trade lists."""
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PenaltyMatchStatus, TacticoMatchStatus, TradeStatus
from app.models.penalty import PenaltyMatch
from app.models.tactico import TacticoMatch
from app.models.trade import TradeOffer
from app.models.user import User
from app.schemas.profile import AttentionOut


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar_one() or 0)


async def get_attention(db: AsyncSession, user: User) -> AttentionOut:
    from app.services.league_service import _unseen_rewards

    now = datetime.now(timezone.utc)
    incoming_trades = await _count(db, select(func.count(TradeOffer.id)).where(
        TradeOffer.receiver_id == user.id, TradeOffer.status == TradeStatus.pending, TradeOffer.expires_at > now,
    ))
    # Friend matches: user_id is the challenger, opponent_user_id the invitee.
    challenges = 0
    active = 0
    for model, pending, in_progress in (
        (TacticoMatch, TacticoMatchStatus.pending_accept, TacticoMatchStatus.in_progress),
        (PenaltyMatch, PenaltyMatchStatus.pending_accept, PenaltyMatchStatus.in_progress),
    ):
        challenges += await _count(db, select(func.count(model.id)).where(
            model.opponent_user_id == user.id, model.status == pending,
        ))
        active += await _count(db, select(func.count(model.id)).where(
            or_(model.user_id == user.id, model.opponent_user_id == user.id),
            model.opponent_user_id.is_not(None), model.status == in_progress,
        ))
    return AttentionOut(
        incoming_trades=incoming_trades,
        match_challenges=challenges,
        active_friend_matches=active,
        league_unseen_rewards=len(await _unseen_rewards(db, user)),
    )
