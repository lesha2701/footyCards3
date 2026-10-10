"""Friends: requests, the friends list and a 7-day activity feed (big pack
pulls, trophies, career finishes) built from data the game already stores."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.card import UserCard
from app.models.career import CareerParticipant, CareerSeason, Friendship
from app.models.enums import NotificationType, Rarity
from app.models.pack import PackOpening, PackOpeningCard
from app.models.player import Player
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.user import User
from app.services.notification_service import notify

FEED_DAYS = 7
FEED_LIMIT = 30


def _pair(a: int, b: int) -> tuple[int, int]:
    return min(a, b), max(a, b)


def _name(user: User) -> str:
    return user.first_name or user.username or "Игрок"


async def _get_pair(db: AsyncSession, a: int, b: int) -> Friendship | None:
    low, high = _pair(a, b)
    return (await db.execute(
        select(Friendship).where(Friendship.user_low == low, Friendship.user_high == high)
    )).scalar_one_or_none()


async def friend_ids(db: AsyncSession, user_id: int) -> list[int]:
    rows = (await db.execute(
        select(Friendship.user_low, Friendship.user_high).where(
            Friendship.status == "accepted",
            (Friendship.user_low == user_id) | (Friendship.user_high == user_id),
        )
    )).all()
    return [high if low == user_id else low for low, high in rows]


async def list_friends(db: AsyncSession, user: User) -> dict:
    rows = (await db.execute(
        select(Friendship).where((Friendship.user_low == user.id) | (Friendship.user_high == user.id))
        .order_by(Friendship.created_at.desc())
    )).scalars().all()
    other_ids = {r.user_high if r.user_low == user.id else r.user_low for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(other_ids)))).scalars().all()} if other_ids else {}
    friends, incoming, outgoing = [], [], []
    for r in rows:
        other = users.get(r.user_high if r.user_low == user.id else r.user_low)
        if other is None or other.is_banned:
            continue
        if r.status == "accepted":
            friends.append({"user": other, "since": r.responded_at or r.created_at})
        elif r.addressee_id == user.id:
            incoming.append({"request_id": r.id, "user": other, "created_at": r.created_at})
        else:
            outgoing.append({"request_id": r.id, "user": other, "created_at": r.created_at})
    return {"friends": friends, "incoming": incoming, "outgoing": outgoing}


async def send_request(db: AsyncSession, user: User, target_id: int) -> str:
    """Returns the resulting status: "pending" or "accepted" (when the other
    player had already asked us — the request becomes mutual)."""
    if target_id == user.id:
        raise ConflictError("Нельзя добавить в друзья самого себя")
    target = await db.get(User, target_id)
    if target is None or target.is_banned:
        raise NotFoundError("Игрок не найден")
    existing = await _get_pair(db, user.id, target_id)
    if existing is not None:
        if existing.status == "accepted":
            raise ConflictError("Вы уже друзья")
        if existing.requester_id == user.id:
            return "pending"
        return await _accept(db, existing, user)
    low, high = _pair(user.id, target_id)
    db.add(Friendship(requester_id=user.id, addressee_id=target_id, user_low=low, user_high=high, status="pending"))
    await notify(
        db, target_id, NotificationType.friend_request, "Заявка в друзья",
        f"{_name(user)} хочет добавить тебя в друзья.", related_object_type="friend_request",
    )
    try:
        await db.commit()
    except IntegrityError:
        # Both players asked each other at the same moment — the unique pair
        # constraint keeps one row; treat it as "already requested".
        await db.rollback()
    return "pending"


async def _accept(db: AsyncSession, row: Friendship, user: User) -> str:
    row.status = "accepted"
    row.responded_at = datetime.now(timezone.utc)
    await notify(
        db, row.requester_id, NotificationType.friend_accepted, "Новый друг",
        f"{_name(user)} принял твою заявку в друзья.", related_object_type="friend_request",
    )
    await db.commit()
    return "accepted"


async def respond(db: AsyncSession, user: User, request_id: int, accept: bool) -> None:
    row = await db.get(Friendship, request_id)
    if row is None or row.addressee_id != user.id or row.status != "pending":
        raise NotFoundError("Заявка не найдена")
    if accept:
        await _accept(db, row, user)
    else:
        await db.delete(row)
        await db.commit()


async def remove(db: AsyncSession, user: User, other_id: int) -> None:
    """Removes a friend, or cancels/declines a pending request either way."""
    row = await _get_pair(db, user.id, other_id)
    if row is None:
        raise NotFoundError("Не в друзьях")
    await db.delete(row)
    await db.commit()


async def relation(db: AsyncSession, user_id: int, other_id: int) -> str:
    """none | friends | outgoing | incoming — for the public profile button."""
    row = await _get_pair(db, user_id, other_id)
    if row is None:
        return "none"
    if row.status == "accepted":
        return "friends"
    return "outgoing" if row.requester_id == user_id else "incoming"


async def incoming_count(db: AsyncSession, user_id: int) -> int:
    return len((await db.execute(
        select(Friendship.id).where(Friendship.addressee_id == user_id, Friendship.status == "pending")
    )).all())


async def feed(db: AsyncSession, user: User) -> list[dict]:
    ids = await friend_ids(db, user.id)
    if not ids:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=FEED_DAYS)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}
    items: list[dict] = []

    pulls = (await db.execute(
        select(PackOpening.user_id, PackOpening.created_at, Player.display_name, Player.rarity)
        .join(PackOpeningCard, PackOpeningCard.opening_id == PackOpening.id)
        .join(UserCard, UserCard.id == PackOpeningCard.user_card_id)
        .join(Player, Player.id == UserCard.player_id)
        .where(PackOpening.user_id.in_(ids), PackOpening.created_at >= since,
               Player.rarity.in_((Rarity.legendary, Rarity.diamond)))
        .order_by(PackOpening.created_at.desc()).limit(FEED_LIMIT)
    )).all()
    for user_id, at, name, rarity in pulls:
        label = "бриллиантовую" if rarity == Rarity.diamond else "легендарную"
        items.append({"kind": "pull", "user_id": user_id, "at": at, "text": f"выбил {label} карточку {name}"})

    trophies = (await db.execute(
        select(UserTrophy.user_id, UserTrophy.granted_at, TrophyDefinition.name)
        .join(TrophyDefinition, TrophyDefinition.id == UserTrophy.trophy_definition_id)
        .where(UserTrophy.user_id.in_(ids), UserTrophy.granted_at >= since)
        .order_by(UserTrophy.granted_at.desc()).limit(FEED_LIMIT)
    )).all()
    for user_id, at, name in trophies:
        items.append({"kind": "trophy", "user_id": user_id, "at": at, "text": f"получил трофей «{name}»"})

    careers = (await db.execute(
        select(CareerParticipant.user_id, CareerSeason.finished_at, CareerParticipant.final_place)
        .join(CareerSeason, CareerSeason.id == CareerParticipant.season_id)
        .where(CareerParticipant.user_id.in_(ids), CareerSeason.status == "finished",
               CareerSeason.finished_at >= since, CareerParticipant.final_place.is_not(None))
        .limit(FEED_LIMIT)
    )).all()
    for user_id, at, place in careers:
        items.append({"kind": "career", "user_id": user_id, "at": at, "text": f"завершил сезон карьеры на {place} месте"})

    for item in items:
        item["at"] = ensure_aware(item["at"])
    items.sort(key=lambda i: i["at"], reverse=True)
    out = []
    for item in items[:FEED_LIMIT]:
        friend = users.get(item["user_id"])
        if friend is None:
            continue
        out.append({**item, "user": friend})
    return out
