"""Club-wide rewards each member claims for themselves — one mechanism for
the «Клубный магазин», weekly club quests and club wars.

A `ClubRewardGrant` holds a reward bundle; every member who was already in
the club when it was created (joined_at <= created_at — so nobody joins a
club just to collect what it bought) may claim it once before it expires.
Claiming locks the member's user row and grants the bundle through
reward_bundle_service; the (grant_id, user_id) unique constraint is what
makes a double-tap or a retry a no-op."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.club import ClubMember
from app.models.club_reward import ClubRewardClaim, ClubRewardGrant
from app.models.enums import CardSource, NotificationType, TransactionType
from app.models.user import User
from app.schemas.club_reward import ClubRewardOut
from app.schemas.monetization import GrantedRewardsOut
from app.services import reward_bundle_service
from app.services.notification_service import notify
from app.services.reward_bundle_service import Bundle
from app.services.wallet_service import lock_user_for_update

CLAIM_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def create_grant(
    db: AsyncSession, club_id: int, source: str, title: str, bundle: Bundle,
    source_ref_id: Optional[int] = None, notify_members: bool = True, notify_text: Optional[str] = None,
) -> Optional[ClubRewardGrant]:
    """Flushes a grant (an empty bundle creates nothing) and tells the
    members; the caller commits."""
    if bundle.is_empty():
        return None
    now = _now()
    grant = ClubRewardGrant(
        club_id=club_id, source=source, source_ref_id=source_ref_id, title=title,
        coins=bundle.coins, pack_id=bundle.pack_id, card_rarity=bundle.card_rarity,
        badge_id=bundle.badge_id, cosmetic_id=bundle.cosmetic_id,
        created_at=now, expires_at=now + timedelta(days=CLAIM_DAYS),
    )
    db.add(grant)
    await db.flush()
    if notify_members:
        member_ids = (await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club_id))).scalars().all()
        for member_id in member_ids:
            await notify(
                db, member_id, NotificationType.club_reward_available, "🎁 Награда клуба",
                notify_text or f"«{title}» — забери свою награду в клубе", related_object_type="club_reward_grant",
                related_object_id=grant.id,
            )
    return grant


def _bundle_of(grant: ClubRewardGrant) -> Bundle:
    return Bundle(
        coins=grant.coins, pack_id=grant.pack_id, card_rarity=grant.card_rarity,
        badge_id=grant.badge_id, cosmetic_id=grant.cosmetic_id,
    )


async def _eligible_query(membership: ClubMember):
    claimed = select(ClubRewardClaim.grant_id).where(ClubRewardClaim.user_id == membership.user_id)
    return (
        select(ClubRewardGrant)
        .where(
            ClubRewardGrant.club_id == membership.club_id,
            ClubRewardGrant.expires_at > _now(),
            ClubRewardGrant.created_at >= membership.joined_at,
            ClubRewardGrant.id.notin_(claimed),
        )
        .order_by(ClubRewardGrant.id)
    )


async def unclaimed(db: AsyncSession, membership: ClubMember) -> list[ClubRewardOut]:
    grants = (await db.execute(await _eligible_query(membership))).scalars().all()
    return [
        ClubRewardOut(
            id=g.id, source=g.source, title=g.title, reward=await reward_bundle_service.describe(db, _bundle_of(g)),
            created_at=g.created_at, expires_at=g.expires_at,
        )
        for g in grants
    ]


async def unclaimed_count(db: AsyncSession, membership: ClubMember) -> int:
    return len((await db.execute(await _eligible_query(membership))).scalars().all())


async def claim(db: AsyncSession, user: User, grant_id: int) -> GrantedRewardsOut:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user.id))).scalar_one_or_none()
    grant = await db.get(ClubRewardGrant, grant_id)
    if membership is None or grant is None or grant.club_id != membership.club_id:
        raise NotFoundError("Награда не найдена")
    if _aware(grant.created_at) < _aware(membership.joined_at):
        raise ConflictError("Эта награда — для тех, кто был в клубе раньше")
    if _aware(grant.expires_at) <= _now():
        raise ConflictError("Срок получения награды истёк")

    locked = await lock_user_for_update(db, user.id)
    try:
        async with db.begin_nested():
            db.add(ClubRewardClaim(grant_id=grant.id, user_id=locked.id))
            await db.flush()
    except IntegrityError:
        raise ConflictError("Награда уже получена") from None
    out = await reward_bundle_service.grant(
        db, locked, _bundle_of(grant),
        tx_type=TransactionType.club_reward, description=f"Награда клуба: {grant.title}",
        card_source=CardSource.club_reward, idempotency_prefix=f"club-reward-{grant.id}-{locked.id}",
        cosmetic_source="club_reward", related_object_type="club_reward_grant", related_object_id=grant.id,
    )
    await db.commit()
    await db.refresh(locked)
    out.new_balance = locked.balance
    return out
