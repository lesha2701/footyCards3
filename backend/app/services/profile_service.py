from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.card import UserCard
from app.models.enums import RARITY_ORDER
from app.models.pack import PackOpening
from app.models.player import Player
from app.models.user import User
from app.schemas.player import PlayerOut
from app.schemas.profile import ProfilePrivateOut, ProfilePublicOut
from app.schemas.user import UserPublicOut


async def _collection_summary(db: AsyncSession, user_id: int) -> tuple[int, int, Player | None]:
    total = (await db.execute(select(func.count(UserCard.id)).where(UserCard.owner_id == user_id))).scalar_one()
    unique = (
        await db.execute(select(func.count(func.distinct(UserCard.player_id))).where(UserCard.owner_id == user_id))
    ).scalar_one()

    rows = (
        await db.execute(
            select(Player).join(UserCard, UserCard.player_id == Player.id).where(UserCard.owner_id == user_id)
        )
    ).scalars().all()
    rarest = None
    for player in rows:
        if rarest is None or (RARITY_ORDER[player.rarity], player.rating) > (RARITY_ORDER[rarest.rarity], rarest.rating):
            rarest = player

    return total, unique, rarest


async def _arena_rank(db: AsyncSession, user: User) -> int:
    higher = (
        await db.execute(select(func.count(User.id)).where(User.arena_rating > user.arena_rating))
    ).scalar_one()
    return higher + 1


async def _packs_opened(db: AsyncSession, user_id: int) -> int:
    return (await db.execute(select(func.count(PackOpening.id)).where(PackOpening.user_id == user_id))).scalar_one()


async def _build_public(db: AsyncSession, user: User) -> ProfilePublicOut:
    total, unique, rarest = await _collection_summary(db, user.id)
    rank = await _arena_rank(db, user)
    packs_opened = await _packs_opened(db, user.id)
    return ProfilePublicOut(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
        level=user.level,
        arena_rating=user.arena_rating,
        arena_rank=rank,
        matches_won=user.matches_won,
        matches_drawn=user.matches_drawn,
        matches_lost=user.matches_lost,
        memory_best_score=user.memory_best_score,
        unique_cards=unique,
        total_cards=total,
        rarest_card=PlayerOut.model_validate(rarest) if rarest else None,
        packs_opened=packs_opened,
    )


async def get_public_profile(db: AsyncSession, user_id: int) -> ProfilePublicOut:
    user = await db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found")
    return await _build_public(db, user)


async def get_private_profile(db: AsyncSession, user: User) -> ProfilePrivateOut:
    public = await _build_public(db, user)
    return ProfilePrivateOut(
        **public.model_dump(),
        telegram_id=user.telegram_id,
        balance=user.balance,
        experience=user.experience,
        is_admin=user.is_admin,
    )


async def search_users(db: AsyncSession, query: str, exclude_user_id: int, limit: int = 20) -> list[UserPublicOut]:
    stmt = select(User).where(User.id != exclude_user_id)
    if query.isdigit():
        stmt = stmt.where((User.id == int(query)) | (User.username.ilike(f"%{query}%")))
    else:
        stmt = stmt.where(User.username.ilike(f"%{query}%"))
    stmt = stmt.limit(limit)
    users = (await db.execute(stmt)).scalars().all()
    return [UserPublicOut.model_validate(u) for u in users]
