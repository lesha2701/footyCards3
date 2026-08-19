from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.league import LeagueTier, UserLeagueRewardClaim
from app.models.pack import Pack
from app.models.user import User
from app.schemas.league import LeagueStatusOut, LeagueTierPublicOut
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
        id=tier.id, name=tier.name, min_rating=tier.min_rating, icon=tier.icon,
        reward_coins=tier.reward_coins, reward_pack_name=await _pack_name(db, tier.reward_pack_id),
        sort_order=tier.sort_order,
    )


async def list_tiers(db: AsyncSession) -> list[LeagueTierPublicOut]:
    tiers = (await db.execute(select(LeagueTier).order_by(LeagueTier.min_rating))).scalars().all()
    return [await _to_public_out(db, t) for t in tiers]


async def get_league_status(db: AsyncSession, user: User) -> LeagueStatusOut:
    total = total_rating(user)
    tiers = (await db.execute(select(LeagueTier).order_by(LeagueTier.min_rating))).scalars().all()

    current = None
    next_tier = None
    for tier in tiers:
        if tier.min_rating <= total:
            current = tier
        elif next_tier is None:
            next_tier = tier

    return LeagueStatusOut(
        total_rating=total, arena_rating=user.arena_rating, tactics_rating=user.tactics_rating,
        penalty_rating=user.penalty_rating,
        current_league=await _to_public_out(db, current) if current else None,
        next_league=await _to_public_out(db, next_tier) if next_tier else None,
        points_to_next=(next_tier.min_rating - total) if next_tier else None,
    )


async def sync_league_rewards_for_user(
    db: AsyncSession, user: User, *, notify_mode: Literal["per_tier", "summary"] = "per_tier"
) -> list[LeagueTier]:
    """Grants every LeagueTier `user` qualifies for (min_rating <= their
    current total rating) but hasn't already claimed. Safe to call
    unconditionally and repeatedly — idempotent via UserLeagueRewardClaim's
    unique (user_id, league_tier_id) constraint. Does not commit; the
    caller's own transaction (already open for the rating-mutating action
    that triggered this) covers it.

    Serves both live play (notify_mode="per_tier": one notification per
    newly-crossed tier, since in practice it's almost always 0 or 1 per
    call) and the admin retroactive backfill (notify_mode="summary": one
    notification total, regardless of how many tiers were granted, so a
    player who jumps several tiers at once doesn't get spammed).
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

    for tier in pending:
        db.add(
            UserLeagueRewardClaim(
                user_id=user.id, league_tier_id=tier.id,
                reward_coins=tier.reward_coins, reward_pack_id=tier.reward_pack_id,
            )
        )
        if tier.reward_coins > 0:
            await credit_coins(
                db, user, tier.reward_coins, TransactionType.league_reward,
                f"Награда за лигу «{tier.name}»", related_object_type="league_tier", related_object_id=tier.id,
            )
        if tier.reward_pack_id:
            from app.services.pack_service import grant_bonus_pack_opening

            await grant_bonus_pack_opening(
                db, user, tier.reward_pack_id,
                idempotency_prefix=f"league-reward-{user.id}-{tier.id}",
                source=CardSource.league_reward,
            )
        if notify_mode == "per_tier":
            await notification_service.notify(
                db, user.id, NotificationType.league_promoted,
                "🏆 Новая лига!",
                f"Ты поднялся в лигу «{tier.name}»! Получено {tier.reward_coins} монет.",
                "league_tier", tier.id,
            )

    if notify_mode == "summary":
        final_tier = pending[-1]
        await notification_service.notify(
            db, user.id, NotificationType.league_promoted,
            "🏆 Твоя лига обновлена!",
            f"Ты сейчас в лиге «{final_tier.name}»! Начислены награды за пройденные лиги.",
            "league_tier", final_tier.id,
        )

    return pending
