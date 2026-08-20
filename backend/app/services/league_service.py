from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.league import LeagueTier, UserLeagueRewardClaim
from app.models.mixins import utcnow
from app.models.pack import Pack
from app.models.user import User
from app.schemas.league import LeagueRewardClaimOut, LeagueStatusOut, LeagueTierPublicOut
from app.services import notification_service
from app.services.wallet_service import credit_coins


def total_rating(user: User) -> int:
    return user.arena_rating + user.tactics_rating + user.penalty_rating


async def _pack_name(db: AsyncSession, pack_id: Optional[int]) -> Optional[str]:
    if pack_id is None:
        return None
    pack = await db.get(Pack, pack_id)
    return pack.name if pack else None


async def _to_public_out(db: AsyncSession, tier: LeagueTier) -> LeagueTierPublicOut:
    return LeagueTierPublicOut(
        id=tier.id, name=tier.name, min_rating=tier.min_rating, color=tier.color, image_path=tier.image_path,
        reward_coins=tier.reward_coins, reward_pack_name=await _pack_name(db, tier.reward_pack_id),
        sort_order=tier.sort_order,
    )


async def _unseen_rewards(db: AsyncSession, user: User) -> list[LeagueRewardClaimOut]:
    claims = (
        await db.execute(
            select(UserLeagueRewardClaim)
            .where(UserLeagueRewardClaim.user_id == user.id, UserLeagueRewardClaim.seen_at.is_(None))
            .order_by(UserLeagueRewardClaim.granted_at)
        )
    ).scalars().all()
    return [
        LeagueRewardClaimOut(
            id=c.id, tier_name=c.tier.name, color=c.tier.color, image_path=c.tier.image_path,
            reward_coins=c.reward_coins, reward_pack_name=await _pack_name(db, c.reward_pack_id),
            granted_at=c.granted_at,
        )
        for c in claims
    ]


async def _floor_rating(db: AsyncSession, user_id: int) -> int:
    """The highest tier threshold `user_id` has ever claimed a reward for —
    claims are created (idempotently) the moment a tier is first crossed
    (see sync_league_rewards_for_user), so this is exactly the "never
    demoted" floor a league promotion should be sticky against."""
    result = await db.execute(
        select(func.max(LeagueTier.min_rating))
        .select_from(UserLeagueRewardClaim)
        .join(LeagueTier, LeagueTier.id == UserLeagueRewardClaim.league_tier_id)
        .where(UserLeagueRewardClaim.user_id == user_id)
    )
    return result.scalar() or 0


def _tier_for_rating(tiers: list[LeagueTier], rating: int) -> tuple[Optional[LeagueTier], Optional[LeagueTier]]:
    """Returns (current, next) for a rating value against an ascending,
    already-sorted tier list — current is the highest tier whose min_rating
    is <= rating, next is the first tier above it."""
    current = None
    next_tier = None
    for tier in tiers:
        if tier.min_rating <= rating:
            current = tier
        elif next_tier is None:
            next_tier = tier
    return current, next_tier


async def _current_league_percent(
    db: AsyncSession, tiers: list[LeagueTier], current: Optional[LeagueTier]
) -> Optional[float]:
    """Share of eligible players (non-banned, non-admin — matching every
    other leaderboard's population) whose own floor-adjusted league equals
    `current`. O(players x tiers) in Python rather than a correlated SQL
    subquery — simple and plenty fast at this project's scale; revisit if
    the player base grows large enough for this to show up in profiling."""
    if current is None or not tiers:
        return None

    rows = (
        await db.execute(
            select(
                (User.arena_rating + User.tactics_rating + User.penalty_rating).label("total"),
                func.coalesce(func.max(LeagueTier.min_rating), 0).label("floor"),
            )
            .select_from(User)
            .outerjoin(UserLeagueRewardClaim, UserLeagueRewardClaim.user_id == User.id)
            .outerjoin(LeagueTier, LeagueTier.id == UserLeagueRewardClaim.league_tier_id)
            .where(User.is_banned.is_(False), User.is_admin.is_(False))
            .group_by(User.id)
        )
    ).all()
    if not rows:
        return None

    in_current = 0
    for total, floor in rows:
        bucket, _ = _tier_for_rating(tiers, max(total, floor))
        if bucket is not None and bucket.id == current.id:
            in_current += 1
    return round(in_current / len(rows) * 100, 1)


async def list_tiers(db: AsyncSession) -> list[LeagueTierPublicOut]:
    tiers = (await db.execute(select(LeagueTier).order_by(LeagueTier.min_rating))).scalars().all()
    return [await _to_public_out(db, t) for t in tiers]


async def get_league_status(db: AsyncSession, user: User) -> LeagueStatusOut:
    total = total_rating(user)
    tiers = (await db.execute(select(LeagueTier).order_by(LeagueTier.min_rating))).scalars().all()

    # A league is sticky: once reached, a later rating dip never demotes the
    # player back down — current/next are computed against the higher of
    # their live rating and their claimed-tier floor, not total_rating alone.
    floor_rating = await _floor_rating(db, user.id)
    current, next_tier = _tier_for_rating(tiers, max(total, floor_rating))

    return LeagueStatusOut(
        total_rating=total, arena_rating=user.arena_rating, tactics_rating=user.tactics_rating,
        penalty_rating=user.penalty_rating,
        current_league=await _to_public_out(db, current) if current else None,
        next_league=await _to_public_out(db, next_tier) if next_tier else None,
        points_to_next=(next_tier.min_rating - total) if next_tier else None,
        current_league_percent=await _current_league_percent(db, tiers, current),
        unseen_rewards=await _unseen_rewards(db, user),
    )


async def mark_rewards_seen(db: AsyncSession, user: User) -> int:
    """Marks every currently-unseen reward claim as seen — purely a UI
    acknowledgment (see UserLeagueRewardClaim.seen_at), does not affect the
    reward itself, which was already granted at tier-cross time. Unlike
    sync_league_rewards_for_user, this touches no balance/pack state, so no
    row-locking precondition applies. Does not commit; the caller's
    transaction covers it."""
    claims = (
        await db.execute(
            select(UserLeagueRewardClaim).where(
                UserLeagueRewardClaim.user_id == user.id, UserLeagueRewardClaim.seen_at.is_(None)
            )
        )
    ).scalars().all()
    now = utcnow()
    for claim in claims:
        claim.seen_at = now
        db.add(claim)
    return len(claims)


async def sync_league_rewards_for_user(
    db: AsyncSession, user: User, *, notify_mode: Literal["per_tier", "summary"] = "per_tier"
) -> list[LeagueTier]:
    """Grants every LeagueTier `user` qualifies for (min_rating <= their
    current total rating) but hasn't already claimed. Safe to call
    unconditionally and repeatedly — idempotent via UserLeagueRewardClaim's
    unique (user_id, league_tier_id) constraint. Does not commit; the
    caller's own transaction (already open for the rating-mutating action
    that triggered this) covers it.

    Precondition: `user` must already be a row-locked User (via
    `wallet_service.lock_user_for_update`) — this function credits coins and
    grants packs but never locks the row itself, exactly like
    `collection_service.grant_collection_rewards_for_new_cards`.

    Serves both live play (notify_mode="per_tier": one notification per
    newly-crossed tier, since in practice it's almost always 0 or 1 per
    call) and the admin retroactive backfill (notify_mode="summary": one
    notification total, regardless of how many tiers were granted, so a
    player who jumps several tiers at once doesn't get spammed).

    Users flagged `game_rewards_blocked` still get the claim row (so the
    tier is consumed and can't be re-farmed for a double payout if the flag
    is later lifted) and the promotion notification, but no coins/pack —
    the same "record the event, zero the reward" shape every other reward
    path uses (match_service, tactico_service, task_service, mini-games).
    """
    total = total_rating(user)
    qualifying = (
        await db.execute(select(LeagueTier).where(LeagueTier.min_rating <= total).order_by(LeagueTier.min_rating))
    ).scalars().all()
    if not qualifying:
        return []

    already_claimed = set(
        (
            await db.execute(
                select(UserLeagueRewardClaim.league_tier_id).where(
                    UserLeagueRewardClaim.user_id == user.id,
                    UserLeagueRewardClaim.league_tier_id.in_([t.id for t in qualifying]),
                )
            )
        ).scalars().all()
    )
    pending = [t for t in qualifying if t.id not in already_claimed]
    if not pending:
        return []

    rewards_blocked = user.game_rewards_blocked
    for tier in pending:
        granted_coins = 0 if rewards_blocked else tier.reward_coins
        granted_pack_id = None if rewards_blocked else tier.reward_pack_id
        db.add(
            UserLeagueRewardClaim(
                user_id=user.id, league_tier_id=tier.id,
                reward_coins=granted_coins, reward_pack_id=granted_pack_id,
            )
        )
        if granted_coins > 0:
            await credit_coins(
                db, user, granted_coins, TransactionType.league_reward,
                f"Награда за лигу «{tier.name}»", related_object_type="league_tier", related_object_id=tier.id,
            )
        if granted_pack_id:
            from app.services.pack_service import grant_bonus_pack_opening

            await grant_bonus_pack_opening(
                db, user, granted_pack_id,
                idempotency_prefix=f"league-reward-{user.id}-{tier.id}",
                source=CardSource.league_reward,
            )
        if notify_mode == "per_tier":
            await notification_service.notify(
                db, user.id, NotificationType.league_promoted,
                "🏆 Новая лига!",
                f"Ты поднялся в лигу «{tier.name}»!"
                + ("" if rewards_blocked else f" Получено {granted_coins} монет."),
                "league_tier", tier.id,
            )

    if notify_mode == "summary":
        final_tier = pending[-1]
        await notification_service.notify(
            db, user.id, NotificationType.league_promoted,
            "🏆 Твоя лига обновлена!",
            f"Ты сейчас в лиге «{final_tier.name}»!"
            + ("" if rewards_blocked else " Начислены награды за пройденные лиги."),
            "league_tier", final_tier.id,
        )

    return pending
