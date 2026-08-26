import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.club import Club, ClubJoinRequest, ClubMember
from app.models.enums import ClubRole, ClubType, TransactionType
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubMemberOut, ClubSummaryOut, ClubUpdate
from app.services.game_config_service import get_config
from app.services.wallet_service import debit_coins, lock_user_for_update

MAX_MEMBERS = 11
MAX_ASSISTANTS = 2


def _generate_invite_code() -> str:
    return secrets.token_urlsafe(6)[:8]


async def _lock_club(db: AsyncSession, club_id: int) -> Club:
    result = await db.execute(select(Club).where(Club.id == club_id).with_for_update())
    club = result.scalar_one_or_none()
    if club is None:
        raise NotFoundError("Клуб не найден")
    return club


async def _member_count(db: AsyncSession, club_id: int) -> int:
    result = await db.execute(select(func.count(ClubMember.id)).where(ClubMember.club_id == club_id))
    return result.scalar_one()


async def _get_membership(db: AsyncSession, user_id: int) -> Optional[ClubMember]:
    result = await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))
    return result.scalar_one_or_none()


async def _require_membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = await _get_membership(db, user_id)
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


def _require_manager(membership: ClubMember) -> None:
    if membership.role not in (ClubRole.captain, ClubRole.assistant):
        raise ForbiddenError("Только капитан или ассистент может это делать")


async def _members_with_users(db: AsyncSession, club_id: int) -> list[ClubMemberOut]:
    rows = (
        await db.execute(
            select(ClubMember, User)
            .join(User, User.id == ClubMember.user_id)
            .where(ClubMember.club_id == club_id)
            .order_by(ClubMember.joined_at)
        )
    ).all()
    return [
        ClubMemberOut(
            user_id=u.id, username=u.username, first_name=u.first_name, avatar_url=u.avatar_url,
            role=m.role, joined_at=m.joined_at,
        )
        for m, u in rows
    ]


async def _club_to_detail(db: AsyncSession, club: Club, requester_user_id: Optional[int]) -> ClubDetailOut:
    members = await _members_with_users(db, club.id)
    my_membership = next((m for m in members if m.user_id == requester_user_id), None)
    is_member = my_membership is not None
    return ClubDetailOut(
        id=club.id, name=club.name, description=club.description, club_type=club.club_type,
        logo_shape=club.logo_shape, logo_color=club.logo_color, captain_id=club.captain_id,
        founded_at=club.founded_at, member_count=len(members), members=members,
        invite_code=club.invite_code if is_member else None,
        my_role=my_membership.role if my_membership else None,
    )


async def create_club(db: AsyncSession, user: User, payload: ClubCreate) -> ClubDetailOut:
    existing = await _get_membership(db, user.id)
    if existing is not None:
        raise ConflictError("Ты уже состоишь в клубе")

    config = await get_config(db)
    locked_user = await lock_user_for_update(db, user.id)
    await debit_coins(
        db, locked_user, config.club_creation_cost_coins, TransactionType.admin_adjustment,
        f"Создание клуба «{payload.name}»",
    )

    club = Club(
        name=payload.name, description=payload.description, club_type=payload.club_type,
        logo_shape=payload.logo_shape, logo_color=payload.logo_color, captain_id=locked_user.id,
        invite_code=_generate_invite_code(),
    )
    db.add(club)
    await db.flush()

    db.add(ClubMember(club_id=club.id, user_id=locked_user.id, role=ClubRole.captain))
    await db.flush()

    await db.commit()
    await db.refresh(club)
    return await _club_to_detail(db, club, requester_user_id=locked_user.id)


async def list_clubs(db: AsyncSession, search: Optional[str]) -> list[ClubSummaryOut]:
    member_count_subq = (
        select(ClubMember.club_id, func.count(ClubMember.id).label("cnt"))
        .group_by(ClubMember.club_id)
        .subquery()
    )
    query = (
        select(Club, func.coalesce(member_count_subq.c.cnt, 0))
        .outerjoin(member_count_subq, member_count_subq.c.club_id == Club.id)
        .order_by(func.coalesce(member_count_subq.c.cnt, 0).desc(), Club.founded_at.desc())
        .limit(100)
    )
    if search:
        query = query.where(Club.name.ilike(f"%{search}%"))
    rows = (await db.execute(query)).all()
    return [
        ClubSummaryOut(
            id=c.id, name=c.name, club_type=c.club_type, logo_shape=c.logo_shape,
            logo_color=c.logo_color, member_count=count,
        )
        for c, count in rows
    ]


async def get_my_club_detail(db: AsyncSession, user: User) -> ClubDetailOut:
    membership = await _require_membership(db, user.id)
    club = await db.get(Club, membership.club_id)
    return await _club_to_detail(db, club, requester_user_id=user.id)


async def get_club_detail(db: AsyncSession, club_id: int, requester_user_id: int) -> ClubDetailOut:
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    return await _club_to_detail(db, club, requester_user_id=requester_user_id)
