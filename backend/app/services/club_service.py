import secrets
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.club import Club, ClubJoinRequest, ClubMember
from app.models.enums import ClubJoinRequestStatus, ClubRole, ClubType, NotificationType, TransactionType
from app.models.user import User
from app.schemas.club import ClubCreate, ClubDetailOut, ClubJoinRequestOut, ClubMemberOut, ClubSummaryOut, ClubUpdate
from app.services.game_config_service import get_config
from app.services.notification_service import notify
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

    existing_name = await db.execute(select(Club).where(Club.name == payload.name))
    if existing_name.scalar_one_or_none() is not None:
        raise ConflictError("Клуб с таким названием уже существует")

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


async def join_open_club(db: AsyncSession, user: User, club_id: int) -> ClubDetailOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    club = await _lock_club(db, club_id)
    if club.club_type != ClubType.open:
        raise ConflictError("Это закрытый клуб — нужна заявка")
    if await _member_count(db, club_id) >= MAX_MEMBERS:
        raise ConflictError("В клубе нет свободных мест")

    db.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.member))
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=user.id)


async def create_join_request(db: AsyncSession, user: User, club_id: int) -> ClubJoinRequestOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    club = await db.get(Club, club_id)
    if club is None:
        raise NotFoundError("Клуб не найден")
    if club.club_type != ClubType.closed:
        raise ConflictError("Это открытый клуб — просто вступи")

    existing = await db.execute(
        select(ClubJoinRequest).where(
            ClubJoinRequest.club_id == club_id, ClubJoinRequest.user_id == user.id,
            ClubJoinRequest.status == ClubJoinRequestStatus.pending,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Заявка уже отправлена")

    request = ClubJoinRequest(club_id=club_id, user_id=user.id)
    db.add(request)
    await db.flush()

    managers = await db.execute(
        select(ClubMember.user_id).where(ClubMember.club_id == club_id, ClubMember.role.in_([ClubRole.captain, ClubRole.assistant]))
    )
    for manager_id in managers.scalars().all():
        await notify(
            db, manager_id, NotificationType.club_join_request_received,
            "Новая заявка в клуб", f"Игрок хочет вступить в «{club.name}»",
            related_object_type="club_join_request", related_object_id=request.id,
        )
    await db.commit()
    await db.refresh(request)
    return ClubJoinRequestOut(
        id=request.id, user_id=user.id, username=user.username, first_name=user.first_name,
        avatar_url=user.avatar_url, created_at=request.created_at, status=request.status,
    )


async def list_join_requests(db: AsyncSession, user: User) -> list[ClubJoinRequestOut]:
    membership = await _require_membership(db, user.id)
    _require_manager(membership)
    rows = (
        await db.execute(
            select(ClubJoinRequest, User)
            .join(User, User.id == ClubJoinRequest.user_id)
            .where(ClubJoinRequest.club_id == membership.club_id, ClubJoinRequest.status == ClubJoinRequestStatus.pending)
            .order_by(ClubJoinRequest.created_at)
        )
    ).all()
    return [
        ClubJoinRequestOut(
            id=r.id, user_id=u.id, username=u.username, first_name=u.first_name,
            avatar_url=u.avatar_url, created_at=r.created_at, status=r.status,
        )
        for r, u in rows
    ]


async def respond_to_join_request(db: AsyncSession, actor: User, request_id: int, accept: bool) -> None:
    membership = await _require_membership(db, actor.id)
    _require_manager(membership)

    request = await db.get(ClubJoinRequest, request_id)
    if request is None or request.club_id != membership.club_id:
        raise NotFoundError("Заявка не найдена")
    if request.status != ClubJoinRequestStatus.pending:
        raise ConflictError("Заявка уже обработана")

    club = await _lock_club(db, membership.club_id)
    if accept:
        if await _get_membership(db, request.user_id) is not None:
            raise ConflictError("Игрок уже состоит в другом клубе")
        if await _member_count(db, club.id) >= MAX_MEMBERS:
            raise ConflictError("В клубе нет свободных мест")
        request.status = ClubJoinRequestStatus.accepted
        db.add(ClubMember(club_id=club.id, user_id=request.user_id, role=ClubRole.member))
        await notify(
            db, request.user_id, NotificationType.club_join_request_accepted,
            "Заявка одобрена", f"Ты теперь в клубе «{club.name}»",
        )
    else:
        request.status = ClubJoinRequestStatus.rejected
        await notify(
            db, request.user_id, NotificationType.club_join_request_rejected,
            "Заявка отклонена", f"Заявка в клуб «{club.name}» отклонена",
        )
    db.add(request)
    await db.commit()


async def _promote_longest_tenured_assistant(db: AsyncSession, club: Club) -> Optional[ClubMember]:
    result = await db.execute(
        select(ClubMember)
        .where(ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant)
        .order_by(ClubMember.joined_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def leave_club(db: AsyncSession, user: User) -> None:
    membership = await _require_membership(db, user.id)
    club = await _lock_club(db, membership.club_id)

    if membership.role == ClubRole.captain:
        successor = await _promote_longest_tenured_assistant(db, club)
        if successor is None:
            # No assistants to take over — the club disbands entirely,
            # per the approved design (even if regular members remain).
            other_member_ids = (
                await db.execute(
                    select(ClubMember.user_id).where(ClubMember.club_id == club.id, ClubMember.user_id != user.id)
                )
            ).scalars().all()
            for member_id in other_member_ids:
                await notify(
                    db, member_id, NotificationType.club_kicked,
                    "Клуб распущен", f"Клуб «{club.name}» распущен — капитан покинул клуб, а ассистента для передачи капитанства не нашлось",
                )

            await db.delete(club)
            await db.commit()
            return
        successor.role = ClubRole.captain
        club.captain_id = successor.user_id
        db.add(successor)
        db.add(club)
        await notify(
            db, successor.user_id, NotificationType.club_captain_transferred,
            "Ты теперь капитан", f"Капитан клуба «{club.name}» покинул клуб — теперь капитан ты",
        )

    await db.delete(membership)
    await db.commit()


async def kick_member(db: AsyncSession, actor: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, actor.id)
    _require_manager(membership)
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id:
        raise NotFoundError("Игрок не в этом клубе")
    if target.role != ClubRole.member:
        raise ForbiddenError("Нельзя исключить капитана или ассистента")

    await db.delete(target)
    await db.flush()
    await notify(db, target_user_id, NotificationType.club_kicked, "Исключение из клуба", f"Тебя исключили из «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=actor.id)


async def appoint_assistant(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может назначать ассистентов")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id or target.role != ClubRole.member:
        raise ConflictError("Можно назначить ассистентом только обычного участника клуба")

    assistant_count = (
        await db.execute(
            select(func.count(ClubMember.id)).where(ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant)
        )
    ).scalar_one()
    if assistant_count >= MAX_ASSISTANTS:
        raise ConflictError("Уже назначено максимальное число ассистентов")

    target.role = ClubRole.assistant
    db.add(target)
    await notify(db, target_user_id, NotificationType.club_role_changed, "Новая роль", f"Ты назначен ассистентом в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def remove_assistant(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может снимать ассистентов")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id or target.role != ClubRole.assistant:
        raise ConflictError("Этот игрок не ассистент в твоём клубе")

    target.role = ClubRole.member
    db.add(target)
    await notify(db, target_user_id, NotificationType.club_role_changed, "Новая роль", f"Ты больше не ассистент в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def transfer_captain(db: AsyncSession, captain: User, target_user_id: int) -> ClubDetailOut:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может передать капитанство")
    club = await _lock_club(db, membership.club_id)

    target = await _get_membership(db, target_user_id)
    if target is None or target.club_id != club.id:
        raise NotFoundError("Игрок не в этом клубе")

    assistant_count = (
        await db.execute(
            select(func.count(ClubMember.id)).where(
                ClubMember.club_id == club.id, ClubMember.role == ClubRole.assistant, ClubMember.user_id != target_user_id,
            )
        )
    ).scalar_one()
    membership.role = ClubRole.assistant if assistant_count < MAX_ASSISTANTS else ClubRole.member
    target.role = ClubRole.captain
    club.captain_id = target_user_id
    db.add_all([membership, target, club])
    await notify(db, target_user_id, NotificationType.club_captain_transferred, "Ты теперь капитан", f"Тебе передали капитанство в «{club.name}»")
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=captain.id)


async def disband_club(db: AsyncSession, captain: User) -> None:
    membership = await _require_membership(db, captain.id)
    if membership.role != ClubRole.captain:
        raise ForbiddenError("Только капитан может распустить клуб")
    club = await _lock_club(db, membership.club_id)

    other_member_ids = (
        await db.execute(select(ClubMember.user_id).where(ClubMember.club_id == club.id, ClubMember.user_id != captain.id))
    ).scalars().all()
    for member_id in other_member_ids:
        await notify(db, member_id, NotificationType.club_kicked, "Клуб распущен", f"Клуб «{club.name}» распущен капитаном")

    await db.delete(club)
    await db.commit()


async def join_by_invite(db: AsyncSession, user: User, invite_code: str) -> ClubDetailOut:
    if await _get_membership(db, user.id) is not None:
        raise ConflictError("Ты уже состоишь в клубе")
    result = await db.execute(select(Club).where(Club.invite_code == invite_code).with_for_update())
    club = result.scalar_one_or_none()
    if club is None:
        raise NotFoundError("Приглашение недействительно")
    if await _member_count(db, club.id) >= MAX_MEMBERS:
        raise ConflictError("В клубе нет свободных мест")

    db.add(ClubMember(club_id=club.id, user_id=user.id, role=ClubRole.member))
    await db.commit()
    return await _club_to_detail(db, club, requester_user_id=user.id)
