"""«Стена клуба»: members write short messages; managers (captain,
vice-captain, assistants) may mark a post as an announcement — every other
member gets it through the bot (club_announcement notification), at most
one announcement per `club_announcement_cooldown_minutes` per club — and
may pin or delete any post. Unread count = posts after the member's
`ClubMember.wall_seen_at`."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.club import Club, ClubMember
from app.models.club_wall import ClubPost
from app.models.enums import NotificationType
from app.models.user import User
from app.schemas.club_wall import ClubPostOut, ClubWallOut
from app.services.club_service import MANAGER_ROLES
from app.services.game_config_service import get_config
from app.services.notification_service import notify

WALL_LIMIT = 50
# Oldest posts beyond this are dropped when a new one is written.
WALL_KEEP = 300


async def _membership(db: AsyncSession, user_id: int) -> ClubMember:
    membership = (await db.execute(select(ClubMember).where(ClubMember.user_id == user_id))).scalar_one_or_none()
    if membership is None:
        raise NotFoundError("Ты не состоишь в клубе")
    return membership


async def unread_count(db: AsyncSession, membership: ClubMember) -> int:
    query = select(func.count(ClubPost.id)).where(
        ClubPost.club_id == membership.club_id, ClubPost.user_id != membership.user_id,
    )
    if membership.wall_seen_at is not None:
        query = query.where(ClubPost.created_at > membership.wall_seen_at)
    return (await db.execute(query)).scalar_one()


async def _cooldown_left(db: AsyncSession, club_id: int, minutes: int) -> int:
    last = (await db.execute(
        select(func.max(ClubPost.created_at)).where(ClubPost.club_id == club_id, ClubPost.is_announcement.is_(True))
    )).scalar_one_or_none()
    if last is None or minutes <= 0:
        return 0
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    left = (last + timedelta(minutes=minutes) - datetime.now(timezone.utc)).total_seconds()
    return max(0, int(left))


async def get_wall(db: AsyncSession, user: User, mark_seen: bool = True) -> ClubWallOut:
    membership = await _membership(db, user.id)
    config = await get_config(db)
    latest_ids = select(ClubPost.id).where(ClubPost.club_id == membership.club_id).order_by(ClubPost.id.desc()).limit(WALL_LIMIT)
    rows = (await db.execute(
        select(ClubPost, User).join(User, User.id == ClubPost.user_id)
        .where(ClubPost.club_id == membership.club_id, (ClubPost.id.in_(latest_ids)) | ClubPost.is_pinned.is_(True))
        .order_by(ClubPost.is_pinned.desc(), ClubPost.id.desc())
    )).all()
    roles = dict((await db.execute(
        select(ClubMember.user_id, ClubMember.role).where(ClubMember.club_id == membership.club_id)
    )).all())
    is_manager = membership.role in MANAGER_ROLES
    posts = [
        ClubPostOut(
            id=p.id, user_id=u.id, username=u.username, first_name=u.first_name, avatar_url=u.avatar_url,
            role=roles.get(u.id), text=p.text, is_announcement=p.is_announcement, is_pinned=p.is_pinned,
            created_at=p.created_at, can_delete=is_manager or u.id == user.id,
        )
        for p, u in rows
    ]
    out = ClubWallOut(
        posts=posts,
        can_announce=is_manager,
        can_pin=is_manager,
        announce_cooldown_seconds=await _cooldown_left(db, membership.club_id, config.club_announcement_cooldown_minutes),
    )
    if mark_seen:
        membership.wall_seen_at = datetime.now(timezone.utc)
        db.add(membership)
        await db.commit()
    return out


async def create_post(db: AsyncSession, user: User, text: str, announce: bool) -> ClubWallOut:
    text = text.strip()
    if not text:
        raise ConflictError("Сообщение пустое")
    membership = await _membership(db, user.id)
    club = (await db.execute(
        select(Club).where(Club.id == membership.club_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if announce:
        if membership.role not in MANAGER_ROLES:
            raise ForbiddenError("Объявления пишут капитан, вице-капитан и ассистенты")
        config = await get_config(db)
        left = await _cooldown_left(db, club.id, config.club_announcement_cooldown_minutes)
        if left > 0:
            raise ConflictError(f"Следующее объявление можно через {left // 60 + 1} мин", details={"seconds": left})

    db.add(ClubPost(club_id=club.id, user_id=user.id, text=text, is_announcement=announce))
    if announce:
        author = user.username or user.first_name or f"#{user.id}"
        member_ids = (await db.execute(
            select(ClubMember.user_id).where(ClubMember.club_id == club.id, ClubMember.user_id != user.id)
        )).scalars().all()
        for member_id in member_ids:
            await notify(
                db, member_id, NotificationType.club_announcement, f"📣 {club.name}",
                f"{author}: {text[:300]}", related_object_type="club", related_object_id=club.id,
            )
    await db.flush()
    # Keep the wall bounded: drop everything older than the newest WALL_KEEP (pinned stay).
    cutoff = (await db.execute(
        select(ClubPost.id).where(ClubPost.club_id == club.id)
        .order_by(ClubPost.id.desc()).offset(WALL_KEEP).limit(1)
    )).scalar_one_or_none()
    if cutoff is not None:
        await db.execute(delete(ClubPost).where(
            ClubPost.club_id == club.id, ClubPost.id <= cutoff, ClubPost.is_pinned.is_(False),
        ))
    await db.commit()
    return await get_wall(db, user)


async def _post_for_manager_or_author(db: AsyncSession, user: User, post_id: int, need_manager: bool) -> tuple[ClubPost, ClubMember]:
    membership = await _membership(db, user.id)
    post: Optional[ClubPost] = await db.get(ClubPost, post_id)
    if post is None or post.club_id != membership.club_id:
        raise NotFoundError("Сообщение не найдено")
    is_manager = membership.role in MANAGER_ROLES
    if need_manager and not is_manager:
        raise ForbiddenError("Закреплять могут капитан, вице-капитан и ассистенты")
    if not need_manager and not (is_manager or post.user_id == user.id):
        raise ForbiddenError("Удалить можно только своё сообщение")
    return post, membership


async def delete_post(db: AsyncSession, user: User, post_id: int) -> ClubWallOut:
    post, _ = await _post_for_manager_or_author(db, user, post_id, need_manager=False)
    await db.delete(post)
    await db.commit()
    return await get_wall(db, user)


async def toggle_pin(db: AsyncSession, user: User, post_id: int) -> ClubWallOut:
    post, _ = await _post_for_manager_or_author(db, user, post_id, need_manager=True)
    post.is_pinned = not post.is_pinned
    db.add(post)
    await db.commit()
    return await get_wall(db, user)
